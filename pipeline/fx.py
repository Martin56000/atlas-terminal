"""Currency conversion into EUR with the delayed Yahoo FX quotes already collected (EURxxx=X).
EURxxx=X is quoted as "xxx per 1 EUR", so amount_in_eur = amount / rate. Missing rate -> None
(never a guessed rate)."""

FX_TICKERS = {"USD": "EURUSD=X", "GBP": "EURGBP=X", "CHF": "EURCHF=X", "SEK": "EURSEK=X",
              "NOK": "EURNOK=X", "DKK": "EURDKK=X", "PLN": "EURPLN=X", "CZK": "EURCZK=X"}


def rates_from_quotes(quotes_data):
    """{currency: units per 1 EUR} from quotes.json data, only for quotes that are ok."""
    rates = {"EUR": 1.0}
    for ccy, tk in FX_TICKERS.items():
        q = (quotes_data or {}).get(tk) or {}
        if q.get("status") == "ok" and q.get("last"):
            rates[ccy] = float(q["last"])
    return rates


def to_eur(amount, currency, rates):
    if amount is None or currency is None:
        return None
    if currency == "GBp":            # London quotes in pence
        amount, currency = amount / 100.0, "GBP"
    rate = rates.get(currency)
    if not rate:
        return None
    return amount / rate
