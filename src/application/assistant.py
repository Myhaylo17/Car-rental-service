import logging
from decimal import Decimal

from src.application import assistant_text as text
from src.application.ports import CatalogReader, RecommendationModel
from src.application.schemas import AssistantOutput, CarFilters, CarOutput
from src.domain.car_names import (
    NameMatch,
    Names,
    canonical_brand,
    match_names,
    same_car_name,
    without_brand_words,
)
from src.domain.errors import DomainError

logger = logging.getLogger(__name__)

# Provider failures after which a catalog-only answer is still valid.
PROVIDER_FAILURES = {"assistant_unavailable", "assistant_timeout"}
# Candidates shown to the ranking model. A larger pool than the 20 cheapest cars
# keeps family SUVs and vans in play; each row is compact (see gemini._ranking_row).
CANDIDATES = 40
MAX_CARS = 5
MAX_LOOKUP_MODELS = 3
RESPONSE_PAGE_SIZE = 20  # value reported in applied_filters, as before


class AssistantService:
    def __init__(self, catalog: CatalogReader, model: RecommendationModel) -> None:
        self.catalog = catalog
        self.model = model

    async def recommend(self, message: str) -> AssistantOutput:
        names = await self.catalog.names()
        lang = text.detect_language(message, names)
        plan = await self._plan(message, names)
        found = match_names(
            names, message, _as_text(plan.get("q")), _as_text(plan.get("brand"))
        )
        self._resolve_names(plan, found, names)
        if found.models:
            return await self._lookup(
                message, plan, found.models[:MAX_LOOKUP_MODELS], lang
            )
        return await self._recommend(message, plan, lang)

    async def _plan(self, message: str, names: Names) -> dict[str, object]:
        try:
            plan = await self.model.plan(message)
        except DomainError as exc:
            named = match_names(names, message)
            if exc.code not in PROVIDER_FAILURES or not (named.models or named.brands):
                raise
            # A named brand/model is resolved from the catalog without the model.
            logger.warning(
                "Assistant plan unavailable (%s); using names only.", exc.code
            )
            plan = {}
        plan = dict(plan)
        if plan.get("max_price") is not None:
            plan["max_price"] = Decimal(str(plan["max_price"])).quantize(
                Decimal("0.01")
            )
        return plan

    @staticmethod
    def _resolve_names(plan: dict[str, object], found: NameMatch, names: Names) -> None:
        """Keep brand and model in separate, catalog-spelled filters.

        The model sometimes returns the full "Toyota RAV4" in q; catalog search
        matches q inside a single field, so that text never matches anything.
        """
        if found.models:
            plan.pop("q", None)
            plan.pop("brand", None)
            if len(found.models) == 1:
                plan["brand"], plan["q"] = found.models[0]
            return
        query = _as_text(plan.get("q"))
        if query:
            rest = without_brand_words(query, names)
            if rest:
                plan["q"] = rest
            else:
                plan.pop("q", None)
        brand = _as_text(plan.get("brand"))
        if brand:
            plan["brand"] = canonical_brand(names, brand) or brand
        elif len(found.brands) == 1:
            plan["brand"] = found.brands[0]

    @staticmethod
    def _filters(plan: dict[str, object], page_size: int) -> CarFilters:
        try:
            return CarFilters.model_validate({**plan, "page_size": page_size})
        except ValueError as exc:
            raise DomainError(
                422, "clarify_request", "Please clarify budget and rental dates."
            ) from exc

    async def _lookup(
        self,
        message: str,
        plan: dict[str, object],
        models: tuple[tuple[str, str], ...],
        lang: str,
    ) -> AssistantOutput:
        """The customer named specific catalog models: answer from catalog rows."""
        extra = {k: v for k, v in plan.items() if k not in ("brand", "q")}
        cars: list[CarOutput] = []
        for brand, model in models:
            page = await self.catalog.search(
                self._filters({**extra, "brand": brand, "q": model}, RESPONSE_PAGE_SIZE)
            )
            cars += [
                c for c in page.items if same_car_name(c.brand, c.model, brand, model)
            ]
        cars = list({car.id: car for car in cars}.values())[:MAX_CARS]
        if len(models) == 1:
            filters = self._filters(
                {**extra, "brand": models[0][0], "q": models[0][1]}, RESPONSE_PAGE_SIZE
            )
        else:
            filters = self._filters(extra, RESPONSE_PAGE_SIZE)
        if cars:
            return AssistantOutput(
                message=text.lookup_message(
                    cars, filters, lang, text.asks_for_specs(message)
                ),
                applied_filters=filters,
                cars=cars,
            )
        # The model exists but the extra conditions (budget, dates) exclude it.
        for brand, model in models:
            page = await self.catalog.search(
                self._filters({"brand": brand, "q": model}, RESPONSE_PAGE_SIZE)
            )
            exact = [
                c for c in page.items if same_car_name(c.brand, c.model, brand, model)
            ]
            if exact:
                return AssistantOutput(
                    message=text.filtered_out_message(exact[0], lang),
                    applied_filters=filters,
                    cars=[],
                )
        return AssistantOutput(
            message=text.not_found_message(filters, lang, []),
            applied_filters=filters,
            cars=[],
        )

    async def _recommend(
        self, message: str, plan: dict[str, object], lang: str
    ) -> AssistantOutput:
        filters = self._filters(plan, CANDIDATES)
        shown = filters.model_copy(update={"page_size": RESPONSE_PAGE_SIZE})
        page = await self.catalog.search(filters)
        if not page.items:
            same_brand: list[CarOutput] = []
            if filters.q and filters.brand:
                brand_only = CarFilters(
                    brand=filters.brand, page_size=RESPONSE_PAGE_SIZE
                )
                same_brand = (await self.catalog.search(brand_only)).items
            return AssistantOutput(
                message=text.not_found_message(shown, lang, same_brand),
                applied_filters=shown,
                cars=[],
            )
        try:
            selected = await self.model.rank(message, page.items)
        except DomainError as exc:
            if exc.code not in PROVIDER_FAILURES:
                raise
            # Deterministic fallback: same catalog search, no AI ordering, no
            # invented data. The distinct message tells it apart from AI picks.
            logger.warning(
                "Assistant rank unavailable (%s); returning catalog order.", exc.code
            )
            return AssistantOutput(
                message=text.fallback_message(lang),
                applied_filters=shown,
                cars=page.items[:MAX_CARS],
            )
        ids = list(dict.fromkeys(selected))[:MAX_CARS]
        if not ids:  # the model found nothing that clearly fits
            return AssistantOutput(
                message=text.no_fit_message(shown, lang),
                applied_filters=shown,
                cars=[],
            )
        # Model output cannot fabricate catalog records, prices or specifications.
        catalog = {car.id: car for car in page.items}
        cars = [catalog[car_id] for car_id in ids if car_id in catalog]
        if not cars:
            logger.warning("Assistant rank returned only unknown car IDs.")
            return AssistantOutput(
                message=text.fallback_message(lang),
                applied_filters=shown,
                cars=page.items[:MAX_CARS],
            )
        return AssistantOutput(
            message=text.recommend_message(cars, shown, lang),
            applied_filters=shown,
            cars=cars,
        )


def _as_text(value: object) -> str | None:
    return value if isinstance(value, str) and value.strip() else None
