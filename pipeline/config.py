"""Static configuration: ticker universe, data source URLs, schedule rules.

Nothing in this file is market data. It only says WHAT to fetch and WHERE.
"""
import os

# --- Ticker universe ----------------------------------------------------------
# kind: stock | etf | index | fx | commodity
# region: US | EU   (decides benchmark, risk-free rate and market hours)
# exchange: exchange_calendars code used for trading hours and holidays

def _t(ticker, name, region, exchange, kind="stock", query_en=None, query_fr=None, adr=None):
    return {
        "ticker": ticker, "name": name, "region": region, "exchange": exchange,
        "kind": kind, "query_en": query_en, "query_fr": query_fr, "adr": adr,
    }

US_WATCH = [
    _t("AAPL", "Apple", "US", "XNYS"),
    _t("MSFT", "Microsoft", "US", "XNYS"),
    _t("NVDA", "NVIDIA", "US", "XNYS"),
    _t("AMZN", "Amazon", "US", "XNYS"),
    _t("GOOGL", "Alphabet", "US", "XNYS"),
    _t("META", "Meta Platforms", "US", "XNYS"),
    _t("TSLA", "Tesla", "US", "XNYS"),
    _t("JPM", "JPMorgan Chase", "US", "XNYS"),
    _t("V", "Visa", "US", "XNYS"),
    _t("SPY", "SPDR S&P 500 ETF", "US", "XNYS", kind="etf"),
    _t("QQQ", "Invesco QQQ (Nasdaq-100)", "US", "XNYS", kind="etf"),
]

US_OVERVIEW_EXTRA = [
    _t("DIA", "SPDR Dow Jones ETF", "US", "XNYS", kind="etf"),
    _t("IWM", "iShares Russell 2000 ETF", "US", "XNYS", kind="etf"),
    _t("^VIX", "CBOE Volatility Index", "US", "XNYS", kind="index"),
]

EU_WATCH = [
    # France
    _t("MC.PA", "LVMH", "EU", "XPAR", query_en="LVMH", query_fr="LVMH"),
    _t("TTE.PA", "TotalEnergies", "EU", "XPAR", query_en="TotalEnergies", query_fr="TotalEnergies", adr="TTE"),
    _t("AIR.PA", "Airbus", "EU", "XPAR", query_en="Airbus", query_fr="Airbus"),
    _t("SAN.PA", "Sanofi", "EU", "XPAR", query_en="Sanofi", query_fr="Sanofi", adr="SNY"),
    _t("OR.PA", "L'Oréal", "EU", "XPAR", query_en="L'Oreal", query_fr="L'Oréal"),
    _t("RMS.PA", "Hermès", "EU", "XPAR", query_en="Hermes International", query_fr="Hermès"),
    _t("BNP.PA", "BNP Paribas", "EU", "XPAR", query_en="BNP Paribas", query_fr="BNP Paribas"),
    _t("SU.PA", "Schneider Electric", "EU", "XPAR", query_en="Schneider Electric", query_fr="Schneider Electric"),
    _t("AI.PA", "Air Liquide", "EU", "XPAR", query_en="Air Liquide", query_fr="Air Liquide"),
    _t("SAF.PA", "Safran", "EU", "XPAR", query_en="Safran", query_fr="Safran"),
    # Germany
    _t("SAP.DE", "SAP", "EU", "XETR", query_en="SAP SE", adr="SAP"),
    _t("SIE.DE", "Siemens", "EU", "XETR", query_en="Siemens AG"),
    _t("ALV.DE", "Allianz", "EU", "XETR", query_en="Allianz"),
    _t("DTE.DE", "Deutsche Telekom", "EU", "XETR", query_en="Deutsche Telekom"),
    _t("MBG.DE", "Mercedes-Benz Group", "EU", "XETR", query_en="Mercedes-Benz Group"),
    # Netherlands
    _t("ASML.AS", "ASML", "EU", "XAMS", query_en="ASML", adr="ASML"),
    _t("INGA.AS", "ING Groep", "EU", "XAMS", query_en="ING Groep"),
    # Switzerland
    _t("NESN.SW", "Nestlé", "EU", "XSWX", query_en="Nestle"),
    _t("NOVN.SW", "Novartis", "EU", "XSWX", query_en="Novartis"),
    _t("ROG.SW", "Roche", "EU", "XSWX", query_en="Roche Holding"),
    # United Kingdom
    _t("AZN.L", "AstraZeneca", "EU", "XLON", query_en="AstraZeneca", adr="AZN"),
    _t("SHEL.L", "Shell", "EU", "XLON", query_en="Shell plc", adr="SHEL"),
    _t("HSBA.L", "HSBC", "EU", "XLON", query_en="HSBC Holdings", adr="HSBC"),
    _t("ULVR.L", "Unilever", "EU", "XLON", query_en="Unilever", adr="UL"),
    # Denmark
    _t("NOVO-B.CO", "Novo Nordisk", "EU", "XCSE", query_en="Novo Nordisk", adr="NVO"),
    # Spain
    _t("ITX.MC", "Inditex", "EU", "XMAD", query_en="Inditex"),
    _t("SAN.MC", "Banco Santander", "EU", "XMAD", query_en="Banco Santander"),
    _t("IBE.MC", "Iberdrola", "EU", "XMAD", query_en="Iberdrola"),
    # Italy
    _t("ENEL.MI", "Enel", "EU", "XMIL", query_en="Enel SpA"),
    _t("ISP.MI", "Intesa Sanpaolo", "EU", "XMIL", query_en="Intesa Sanpaolo"),
    _t("RACE.MI", "Ferrari", "EU", "XMIL", query_en="Ferrari NV"),
]

EU_INDICES = [
    _t("^STOXX50E", "Euro Stoxx 50", "EU", "XETR", kind="index"),
    _t("^FCHI", "CAC 40", "EU", "XPAR", kind="index"),
    _t("^GDAXI", "DAX", "EU", "XETR", kind="index"),
    _t("^FTSE", "FTSE 100", "EU", "XLON", kind="index"),
    _t("^AEX", "AEX", "EU", "XAMS", kind="index"),
    _t("^SSMI", "SMI", "EU", "XSWX", kind="index"),
    _t("^IBEX", "IBEX 35", "EU", "XMAD", kind="index"),
    _t("FTSEMIB.MI", "FTSE MIB", "EU", "XMIL", kind="index"),
]

FX_COMMOD = [
    _t("EURUSD=X", "EUR/USD", "EU", "XLON", kind="fx"),
    _t("BZ=F", "Brent", "US", "XNYS", kind="commodity"),
    _t("GC=F", "Gold", "US", "XNYS", kind="commodity"),
]

UNIVERSE = US_WATCH + US_OVERVIEW_EXTRA + EU_WATCH + EU_INDICES + FX_COMMOD
BY_TICKER = {t["ticker"]: t for t in UNIVERSE}

# Tickers a visitor can put in the watchlist (risk metrics are computed for these)
WATCHLIST_UNIVERSE = [t["ticker"] for t in US_WATCH + EU_WATCH]
DEFAULT_WATCHLIST = [t["ticker"] for t in US_WATCH] + ["MC.PA", "ASML.AS", "SAP.DE"]

BENCHMARK = {"US": "SPY", "EU": "^STOXX50E"}
RISK_FREE_SERIES = {"US": "DGS3MO", "EU": "ECBDFR"}

# Expected quote currency per exchange suffix (used to label prices and to
# detect London quotes in pence). Yahoo's own currency field wins when present.
SUFFIX_CURRENCY = {".PA": "EUR", ".DE": "EUR", ".AS": "EUR", ".MC": "EUR", ".MI": "EUR",
                   ".SW": "CHF", ".L": "GBp", ".CO": "DKK"}

# --- Sources ---------------------------------------------------------------------
FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
FRED_SERIES = ["DFF", "DGS3MO", "DGS2", "DGS10", "CPIAUCSL", "UNRATE"]
# Primary US sources used when FRED does not answer (FRED often times out from cloud IPs)
TREASURY_URL = ("https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/"
                "{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv")
NYFED_EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json?startDate={start}&endDate={end}"
BLS_URL = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
BLS_SERIES = {"CPIAUCSL": "CUSR0000SA0", "UNRATE": "LNS14000000"}  # same series FRED republishes
ECB_URL ="https://data-api.ecb.europa.eu/service/data/{key}?format=csvdata"
# The ECB replaced the ICP dataset with HICP in Feb 2026; the most recent one wins.
ECB_HICP_KEYS = ["HICP/M.U2.N.000000.4D0.ANR", "ICP/M.U2.N.000000.4.ANR"]
ECB_DFR_KEY = "FM/D.U2.EUR.4F.KR.DFR.LEV"

GOOGLE_NEWS_EN = "https://news.google.com/rss/search?q={q}+stock&hl=en-US&gl=US&ceid=US:en"
GOOGLE_NEWS_FR = "https://news.google.com/rss/search?q={q}+action&hl=fr&gl=FR&ceid=FR:fr"
NEWS_PER_LANG = 10

SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"
SEC_SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
SEC_MAX_RPS = 5


def sec_user_agent():
    email = os.environ.get("SEC_CONTACT_EMAIL", "").strip()
    if not email:
        raise RuntimeError("SEC_CONTACT_EMAIL is not set (required by SEC EDGAR fair-access policy)")
    return f"Atlas Terminal (student project) {email}"


FINBERT_MODEL = "ProsusAI/finbert"

# --- Schedule (all weekdays; owner uses the site 09:00-18:30 Europe/Paris) ---------
PARIS = "Europe/Paris"
NEW_YORK = "America/New_York"
DAILY_BATCH_AT = "08:30"      # Paris
EU_CLOSE_RUN_AT = "17:40"     # Paris (first cron tick after this does the EU close run)
OWNER_DAY_END = "18:30"       # Paris: no intraday updates after this
NEWS_START = "09:00"          # Paris
NEWS_EVERY_MIN = 55           # ~hourly, tolerant of cron jitter
HISTORY_YEARS = 5
RISK_WINDOW = 252
