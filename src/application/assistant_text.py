"""Reply texts for the assistant, built only from catalog rows and applied filters.

No facts are invented: every number and attribute comes from ``CarOutput`` or from
the filters that were actually applied. Ukrainian is the default; a message written
in Latin script without Cyrillic gets English text.
"""

import re
from collections.abc import Sequence
from decimal import Decimal

from src.application.schemas import CarFilters, CarOutput
from src.domain.car_names import Names, known_words

_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
_LATIN_WORD = re.compile(r"[A-Za-z]{2,}")
_SPECS = re.compile(
    r"характеристик|параметр|специфікац|розкаж|specs?\b|specification|details?\b|"
    r"tell me about|about\b",
    re.IGNORECASE,
)

LABELS = {
    "uk": {
        "category": {
            "economy": "економ-клас",
            "sedan": "седан",
            "suv": "SUV",
            "premium": "преміум-клас",
            "van": "мікроавтобус",
        },
        "transmission": {
            "automatic": "автоматична коробка",
            "manual": "механічна коробка",
        },
        "fuel": {
            "petrol": "бензин",
            "diesel": "дизель",
            "hybrid": "гібрид",
            "electric": "електро",
        },
    },
    "en": {
        "category": {
            "economy": "economy",
            "sedan": "sedan",
            "suv": "SUV",
            "premium": "premium",
            "van": "van",
        },
        "transmission": {"automatic": "automatic", "manual": "manual"},
        "fuel": {
            "petrol": "petrol",
            "diesel": "diesel",
            "hybrid": "hybrid",
            "electric": "electric",
        },
    },
}

TEXTS = {
    "uk": {
        "lookup_one": "У каталозі є {cars}.",
        "lookup_many": "У каталозі є кілька відповідних варіантів: {cars}.",
        "specs": " Інших технічних характеристик (наприклад, об'єму багажника чи "
        "витрати пального) у каталозі немає.",
        "dates": " Показано лише авто, вільні на ці дати за поточними бронюваннями; "
        "остаточну доступність підтвердить бронювання.",
        "ask_dates": " Назвіть дати, і я перевірю наявність.",
        "filtered_out": "Авто є в каталозі: {cars}. Проте під ваші поточні умови "
        "(бюджет, дати чи інші фільтри) воно не підійшло. Можна змінити бюджет "
        "або дати, і я перевірю ще раз.",
        "recommend_one": "Під ваш запит підійде {cars}.",
        "recommend_many": "Під ваш запит варто звернути увагу на такі варіанти: "
        "{cars}.",
        "more": " Інші підходящі авто показані в картках.",
        "no_model": "На жаль, {named} у каталозі не знайшлося.",
        "same_brand": " Зате з {brand} зараз є: {models}. Показати докладніше "
        "якусь із них?",
        "offer": " Можу підібрати схожі авто за типом кузова, бюджетом чи "
        "кількістю місць, підкажіть, що для вас важливо.",
        "not_found": "На жаль, за цими умовами авто не знайшлося.{suggest} "
        "Підкажіть, що вам підходить, і я пошукаю ще.",
        "not_found_empty": "На жаль, за цим запитом нічого не знайшлося. Опишіть, "
        "будь ласка, для чого потрібне авто, скільки буде пасажирів і який "
        "бюджет на добу.",
        "clarify": "Щоб підібрати вдалий варіант, підкажіть: для яких поїздок і "
        "на скільки людей вам потрібне авто?",
        "no_fit": "Серед знайдених авто я не бачу явно вдалого для вашого "
        "запиту.{suggest} Або опишіть задачу докладніше, і я підберу точніше.",
        "fallback": "AI-підбір тимчасово недоступний, тому показано перші авто "
        "за вашими фільтрами в порядку каталогу (без AI-ранжування). "
        "Характеристики та ціни наведені в картках.",
        "can": " Можна {options}.",
        "or": " або ",
        "budget": "збільшити бюджет (зараз до {price} {currency} на добу)",
        "category": "розглянути інший тип авто",
        "transmission": "допустити іншу коробку передач",
        "fuel": "розглянути інший тип пального",
        "seats": "зменшити кількість місць",
        "dates_change": "обрати інші дати",
        "price_per_day": "{price} {currency} на добу",
    },
    "en": {
        "lookup_one": "The catalog has {cars}.",
        "lookup_many": "We have several matching options: {cars}.",
        "specs": " The catalog has no other technical specifications (such as "
        "trunk size or fuel consumption).",
        "dates": " Only cars free on these dates per current bookings are shown; "
        "final availability is confirmed when booking.",
        "ask_dates": " Tell me the dates and I will check availability.",
        "filtered_out": "The car is in the catalog: {cars}. However, it did not "
        "fit your current conditions (budget, dates or other filters). You can "
        "change the budget or dates and I will check again.",
        "recommend_one": "{cars} should suit your request.",
        "recommend_many": "These options look worth a closer look: {cars}.",
        "more": " Other suitable cars are shown in the cards.",
        "no_model": "Unfortunately, {named} is not in the catalog.",
        "same_brand": " The {brand} cars we have are: {models}. Want details on "
        "any of them?",
        "offer": " I can suggest similar cars by body type, budget or number of "
        "seats, so tell me what matters to you.",
        "not_found": "Unfortunately, no cars matched these conditions.{suggest} "
        "Tell me what works for you and I will search again.",
        "not_found_empty": "Unfortunately, nothing matched this request. Please "
        "tell me what the car is for, how many passengers there will be and the "
        "daily budget.",
        "clarify": "To pick a good option, could you tell me what trips the car "
        "is for and how many people will travel?",
        "no_fit": "I don't see a clearly good fit for your request among the "
        "cars found.{suggest} Or describe the task in more detail and I will "
        "narrow it down.",
        "fallback": "AI selection is temporarily unavailable, so the first cars "
        "matching your filters are shown in catalog order (no AI ranking). "
        "Specifications and prices are in the cards.",
        "can": " You could {options}.",
        "or": " or ",
        "budget": "raise the budget (currently up to {price} {currency} per day)",
        "category": "consider another car type",
        "transmission": "allow another transmission",
        "fuel": "consider another fuel type",
        "seats": "reduce the number of seats",
        "dates_change": "choose other dates",
        "price_per_day": "{price} {currency} per day",
    },
}


def detect_language(message: str, names: Names) -> str:
    if _CYRILLIC.search(message):
        return "uk"
    known = known_words(names)
    extra = [w for w in _LATIN_WORD.findall(message) if w.casefold() not in known]
    return "en" if len(extra) >= 2 else "uk"


def asks_for_specs(message: str) -> bool:
    return bool(_SPECS.search(message))


def _money(amount: Decimal) -> str:
    return f"{amount:.0f}" if amount == amount.to_integral_value() else f"{amount:.2f}"


def _seats(count: int, lang: str) -> str:
    if lang == "en":
        return f"{count} seat" + ("" if count == 1 else "s")
    last, last2 = count % 10, count % 100
    if last == 1 and last2 != 11:
        word = "місце"
    elif 2 <= last <= 4 and not 12 <= last2 <= 14:
        word = "місця"
    else:
        word = "місць"
    return f"{count} {word}"


def car_line(car: CarOutput, lang: str) -> str:
    labels = LABELS[lang]
    facts = [
        labels["category"].get(car.category, car.category),
        labels["transmission"].get(car.transmission, car.transmission),
        labels["fuel"].get(car.fuel_type, car.fuel_type),
        _seats(car.seats, lang),
        TEXTS[lang]["price_per_day"].format(
            price=_money(car.daily_price), currency=car.currency
        ),
    ]
    return f"{car.brand} {car.model} ({car.year}): " + ", ".join(facts)


def _lines(cars: Sequence[CarOutput], lang: str, limit: int = 3) -> str:
    return "; ".join(car_line(car, lang) for car in cars[:limit])


def _suggest(filters: CarFilters, lang: str) -> str:
    text = TEXTS[lang]
    options = []
    if filters.max_price is not None:
        options.append(
            text["budget"].format(price=_money(filters.max_price), currency="UAH")
        )
    if filters.category:
        options.append(text["category"])
    if filters.transmission:
        options.append(text["transmission"])
    if filters.fuel_type:
        options.append(text["fuel"])
    if filters.min_seats:
        options.append(text["seats"])
    if filters.start_date:
        options.append(text["dates_change"])
    if not options:
        return ""
    joined = (
        options[0]
        if len(options) == 1
        else ", ".join(options[:-1]) + text["or"] + options[-1]
    )
    return text["can"].format(options=joined)


def _availability(filters: CarFilters, lang: str, ask: bool = True) -> str:
    text = TEXTS[lang]
    if filters.start_date:
        return text["dates"]
    return text["ask_dates"] if ask else ""


def lookup_message(
    cars: Sequence[CarOutput], filters: CarFilters, lang: str, specs: bool
) -> str:
    text = TEXTS[lang]
    key = "lookup_one" if len(cars) == 1 else "lookup_many"
    message = text[key].format(cars=_lines(cars, lang, 5))
    if specs:
        message += text["specs"]
    return message + _availability(filters, lang)


def filtered_out_message(car: CarOutput, lang: str) -> str:
    return TEXTS[lang]["filtered_out"].format(cars=car_line(car, lang))


def recommend_message(cars: Sequence[CarOutput], filters: CarFilters, lang: str) -> str:
    text = TEXTS[lang]
    key = "recommend_one" if len(cars) == 1 else "recommend_many"
    message = text[key].format(cars=_lines(cars, lang))
    if len(cars) > 3:
        message += text["more"]
    return message + _availability(filters, lang, ask=False)


def not_found_message(
    filters: CarFilters, lang: str, same_brand: Sequence[CarOutput]
) -> str:
    text = TEXTS[lang]
    if filters.q:
        named = f"{filters.brand or ''} {filters.q}".strip()
        message = text["no_model"].format(named=f"«{named}»")
        if same_brand and filters.brand:
            models = ", ".join(dict.fromkeys(car.model for car in same_brand))
            return message + text["same_brand"].format(
                brand=filters.brand, models=models
            )
        return message + text["offer"]
    suggest = _suggest(filters, lang)
    if not suggest and not filters.brand:
        return text["not_found_empty"]
    return text["not_found"].format(suggest=suggest)


def no_fit_message(filters: CarFilters, lang: str) -> str:
    suggest = _suggest(filters, lang)
    if not suggest and not _has_filters(filters):
        return TEXTS[lang]["clarify"]
    return TEXTS[lang]["no_fit"].format(suggest=suggest)


def fallback_message(lang: str) -> str:
    return TEXTS[lang]["fallback"]


def _has_filters(filters: CarFilters) -> bool:
    return any(
        value is not None
        for value in (
            filters.q,
            filters.brand,
            filters.category,
            filters.transmission,
            filters.fuel_type,
            filters.min_seats,
            filters.min_price,
            filters.max_price,
            filters.start_date,
        )
    )
