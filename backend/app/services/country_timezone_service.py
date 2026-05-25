from dataclasses import dataclass

import pycountry
import pytz


# Multi-timezone countries resolved to capital-region timezone.
CAPITAL_TIMEZONE_OVERRIDES: dict[str, str] = {
    "AU": "Australia/Sydney",
    "BR": "America/Sao_Paulo",
    "CA": "America/Toronto",
    "CL": "America/Santiago",
    "EC": "America/Guayaquil",
    "ES": "Europe/Madrid",
    "FM": "Pacific/Pohnpei",
    "GL": "America/Nuuk",
    "ID": "Asia/Jakarta",
    "KI": "Pacific/Tarawa",
    "KZ": "Asia/Almaty",
    "MH": "Pacific/Majuro",
    "MN": "Asia/Ulaanbaatar",
    "MX": "America/Mexico_City",
    "NZ": "Pacific/Auckland",
    "PF": "Pacific/Tahiti",
    "PG": "Pacific/Port_Moresby",
    "PT": "Europe/Lisbon",
    "RU": "Europe/Moscow",
    "UA": "Europe/Kyiv",
    "UM": "Pacific/Midway",
    "US": "America/New_York",
}

COUNTRY_ALIASES: dict[str, str] = {
    "usa": "US",
    "us": "US",
    "united states": "US",
    "uk": "GB",
    "united kingdom": "GB",
    "uae": "AE",
}


@dataclass(frozen=True)
class CountryTimezoneResolution:
    timezone: str | None
    country_code: str | None
    country_name: str | None
    error: str | None


def resolve_country_timezone(raw_country: str) -> CountryTimezoneResolution:
    query = raw_country.strip()
    if not query:
        return CountryTimezoneResolution(
            timezone=None,
            country_code=None,
            country_name=None,
            error="Usage: /digest_schedule country <country>",
        )

    normalized_key = query.lower()
    alias_code = COUNTRY_ALIASES.get(normalized_key)
    country = None

    if alias_code:
        country = pycountry.countries.get(alpha_2=alias_code)
    if country is None:
        try:
            country = pycountry.countries.lookup(query)
        except LookupError:
            return CountryTimezoneResolution(
                timezone=None,
                country_code=None,
                country_name=None,
                error=f"Unknown country '{query}'. Example: /digest_schedule country Singapore",
            )

    country_code = str(getattr(country, "alpha_2", "")).upper()
    if not country_code:
        return CountryTimezoneResolution(
            timezone=None,
            country_code=None,
            country_name=None,
            error=f"Unable to resolve timezone for '{query}'.",
        )

    if country_code in CAPITAL_TIMEZONE_OVERRIDES:
        timezone_name = CAPITAL_TIMEZONE_OVERRIDES[country_code]
    else:
        timezone_candidates = pytz.country_timezones.get(country_code, [])
        if not timezone_candidates:
            return CountryTimezoneResolution(
                timezone=None,
                country_code=country_code,
                country_name=getattr(country, "name", None),
                error=f"No timezone mapping available for '{query}'.",
            )
        timezone_name = timezone_candidates[0]

    return CountryTimezoneResolution(
        timezone=timezone_name,
        country_code=country_code,
        country_name=getattr(country, "name", None),
        error=None,
    )
