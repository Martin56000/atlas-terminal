"""Static configuration: ticker universe, data source URLs, schedule rules.

Nothing in this file is market data. It only says WHAT to fetch and WHERE.
"""
import os

# --- Ticker universe ----------------------------------------------------------
# kind: stock | etf | index | fx | commodity
# region: US | EU   (decides benchmark, risk-free rate and market hours)
# exchange: exchange_calendars code used for trading hours and holidays

SUFFIX_COUNTRY = {".PA": "FR", ".DE": "DE", ".AS": "NL", ".SW": "CH", ".L": "GB", ".CO": "DK", ".MC": "ES", ".MI": "IT",
                  ".BR": "BE", ".ST": "SE", ".OL": "NO", ".HE": "FI", ".LS": "PT"}


def _t(ticker, name, region, exchange, kind="stock", query_en=None, query_fr=None, adr=None, segment="large"):
    suffix = "." + ticker.split(".")[-1] if "." in ticker else ""
    return {
        "ticker": ticker, "name": name, "region": region, "exchange": exchange,
        "kind": kind, "query_en": query_en, "query_fr": query_fr, "adr": adr,
        "segment": segment, "country": SUFFIX_COUNTRY.get(suffix, "US" if region == "US" else None),
    }


def _smid(ticker, name, exchange, query_en=None, query_fr=None):
    """European small / mid cap (news refreshed twice a day, no free fundamentals source)."""
    q_fr = query_fr if query_fr is not None else (name if ticker.endswith(".PA") else None)
    return _t(ticker, name, "EU", exchange, query_en=query_en or name, query_fr=q_fr, segment="smid")

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

EU_SMID = [
    # France (Euronext Paris)
    _smid("VCT.PA", "Vicat", "XPAR", query_en="Vicat cement"),
    _smid("TRI.PA", "Trigano", "XPAR"),
    _smid("LSS.PA", "Lectra", "XPAR"),
    _smid("VIRP.PA", "Virbac", "XPAR"),
    _smid("SOP.PA", "Sopra Steria", "XPAR"),
    _smid("IPS.PA", "Ipsos", "XPAR"),
    _smid("SK.PA", "SEB", "XPAR", query_en="Groupe SEB", query_fr="Groupe SEB"),
    _smid("RUI.PA", "Rubis", "XPAR"),
    _smid("ELIS.PA", "Elis", "XPAR", query_en="Elis SA", query_fr="Elis"),
    _smid("SPIE.PA", "Spie", "XPAR", query_en="SPIE SA", query_fr="Spie"),
    _smid("NEX.PA", "Nexans", "XPAR"),
    _smid("NK.PA", "Imerys", "XPAR"),
    _smid("ATE.PA", "Alten", "XPAR"),
    _smid("ITP.PA", "Interparfums", "XPAR"),
    _smid("GTT.PA", "Gaztransport & Technigaz", "XPAR", query_en="GTT Gaztransport", query_fr="GTT Gaztransport"),
    _smid("WAVE.PA", "Wavestone", "XPAR"),
    _smid("MTU.PA", "Manitou", "XPAR"),
    _smid("FNAC.PA", "Fnac Darty", "XPAR"),
    _smid("QDT.PA", "Quadient", "XPAR"),
    _smid("MRN.PA", "Mersen", "XPAR"),
    _smid("SAVE.PA", "Savencia", "XPAR"),
    _smid("BEN.PA", "Bénéteau", "XPAR", query_en="Beneteau"),
    _smid("ALLDL.PA", "Groupe LDLC", "XPAR", query_en="LDLC"),
    _smid("LACR.PA", "Lacroix Group", "XPAR", query_fr="Lacroix Group"),
    _smid("JCQ.PA", "Jacquet Metals", "XPAR"),
    _smid("THEP.PA", "Thermador Groupe", "XPAR"),
    _smid("DBG.PA", "Derichebourg", "XPAR"),
    _smid("KOF.PA", "Kaufman & Broad", "XPAR"),
    _smid("NXI.PA", "Nexity", "XPAR"),
    _smid("BON.PA", "Bonduelle", "XPAR"),
    _smid("EXA.PA", "Exail Technologies", "XPAR"),
    _smid("PIG.PA", "Haulotte", "XPAR"),
    _smid("GBT.PA", "Guerbet", "XPAR"),
    # Germany (Xetra)
    _smid("HAG.DE", "Hensoldt", "XETR"),
    _smid("RAA.DE", "Rational", "XETR", query_en="Rational AG"),
    _smid("PUM.DE", "Puma", "XETR", query_en="Puma SE"),
    _smid("BOSS.DE", "Hugo Boss", "XETR"),
    _smid("NDA.DE", "Aurubis", "XETR"),
    _smid("FIE.DE", "Fielmann", "XETR"),
    _smid("SIX2.DE", "Sixt", "XETR", query_en="Sixt SE"),
    _smid("JEN.DE", "Jenoptik", "XETR"),
    _smid("KRN.DE", "Krones", "XETR"),
    _smid("KGX.DE", "KION Group", "XETR"),
    # Italy (Borsa Italiana)
    _smid("BC.MI", "Brunello Cucinelli", "XMIL"),
    _smid("AMP.MI", "Amplifon", "XMIL"),
    _smid("REY.MI", "Reply", "XMIL", query_en="Reply SpA"),
    _smid("DLG.MI", "De'Longhi", "XMIL", query_en="De'Longhi"),
    _smid("IP.MI", "Interpump", "XMIL"),
    # Spain (BME)
    _smid("VIS.MC", "Viscofan", "XMAD"),
    _smid("EBRO.MC", "Ebro Foods", "XMAD"),
    _smid("CIE.MC", "CIE Automotive", "XMAD"),
    _smid("FDR.MC", "Fluidra", "XMAD"),
    # Netherlands (Euronext Amsterdam)
    _smid("BESI.AS", "BE Semiconductor", "XAMS", query_en="BE Semiconductor Besi"),
    _smid("AALB.AS", "Aalberts", "XAMS"),
    _smid("ARCAD.AS", "Arcadis", "XAMS"),
    _smid("IMCD.AS", "IMCD", "XAMS", query_en="IMCD NV"),
    # Denmark (Nasdaq Copenhagen)
    _smid("PNDORA.CO", "Pandora", "XCSE", query_en="Pandora jewelry"),
    _smid("ROCK-B.CO", "Rockwool", "XCSE"),
    # United Kingdom (FTSE 250)
    _smid("GAW.L", "Games Workshop", "XLON"),
    _smid("BWY.L", "Bellway", "XLON"),
    _smid("GRG.L", "Greggs", "XLON"),
    _smid("CCC.L", "Computacenter", "XLON"),
    # Switzerland (SIX)
    _smid("BEAN.SW", "Belimo", "XSWX"),
    _smid("TECN.SW", "Tecan", "XSWX"),
    _smid("VACN.SW", "VAT Group", "XSWX"),
]

def _eu(ticker, name, exchange, segment="large", query_en=None, query_fr=None):
    """Additional European stock (news refreshed once a day)."""
    q_fr = query_fr if query_fr is not None else (name if ticker.endswith(".PA") else None)
    return _t(ticker, name, "EU", exchange, query_en=query_en or name, query_fr=q_fr, segment=segment)


EU_MORE = [
    # France: rest of the SBF 120
    _eu("ACA.PA", "Crédit Agricole", "XPAR", query_en="Credit Agricole SA"),
    _eu("GLE.PA", "Société Générale", "XPAR", query_en="Societe Generale"),
    _eu("CS.PA", "AXA", "XPAR", query_en="AXA SA"),
    _eu("BN.PA", "Danone", "XPAR"),
    _eu("DG.PA", "Vinci", "XPAR", query_en="Vinci SA"),
    _eu("EL.PA", "EssilorLuxottica", "XPAR"),
    _eu("KER.PA", "Kering", "XPAR"),
    _eu("RI.PA", "Pernod Ricard", "XPAR"),
    _eu("CAP.PA", "Capgemini", "XPAR"),
    _eu("ENGI.PA", "Engie", "XPAR"),
    _eu("ORA.PA", "Orange", "XPAR", query_en="Orange SA telecom", query_fr="Orange opérateur"),
    _eu("VIE.PA", "Veolia", "XPAR"),
    _eu("SGO.PA", "Saint-Gobain", "XPAR"),
    _eu("LR.PA", "Legrand", "XPAR"),
    _eu("ML.PA", "Michelin", "XPAR"),
    _eu("STLAP.PA", "Stellantis", "XPAR"),
    _eu("RNO.PA", "Renault", "XPAR"),
    _eu("HO.PA", "Thales", "XPAR"),
    _eu("PUB.PA", "Publicis", "XPAR"),
    _eu("DSY.PA", "Dassault Systèmes", "XPAR", query_en="Dassault Systemes"),
    _eu("EN.PA", "Bouygues", "XPAR"),
    _eu("CA.PA", "Carrefour", "XPAR"),
    _eu("AC.PA", "Accor", "XPAR"),
    _eu("URW.PA", "Unibail-Rodamco-Westfield", "XPAR"),
    _eu("STMPA.PA", "STMicroelectronics", "XPAR"),
    _eu("FGR.PA", "Eiffage", "XPAR"),
    _eu("AKE.PA", "Arkema", "XPAR"),
    _eu("BVI.PA", "Bureau Veritas", "XPAR"),
    _eu("ERF.PA", "Eurofins Scientific", "XPAR"),
    _eu("EDEN.PA", "Edenred", "XPAR"),
    _eu("AM.PA", "Dassault Aviation", "XPAR"),
    _eu("AMUN.PA", "Amundi", "XPAR"),
    _eu("BIM.PA", "bioMérieux", "XPAR", query_en="bioMerieux"),
    _eu("RXL.PA", "Rexel", "XPAR"),
    _eu("ALO.PA", "Alstom", "XPAR"),
    _eu("VIV.PA", "Vivendi", "XPAR", segment="smid"),
    _eu("COV.PA", "Covivio", "XPAR", segment="smid"),
    _eu("GFC.PA", "Gecina", "XPAR", segment="smid"),
    _eu("LI.PA", "Klépierre", "XPAR", segment="smid", query_en="Klepierre"),
    _eu("RCO.PA", "Rémy Cointreau", "XPAR", segment="smid", query_en="Remy Cointreau"),
    _eu("SW.PA", "Sodexo", "XPAR", segment="smid"),
    _eu("TEP.PA", "Teleperformance", "XPAR", segment="smid"),
    _eu("UBI.PA", "Ubisoft", "XPAR", segment="smid"),
    _eu("VK.PA", "Vallourec", "XPAR", segment="smid"),
    _eu("AF.PA", "Air France-KLM", "XPAR", segment="smid"),
    _eu("ADP.PA", "Aéroports de Paris", "XPAR", segment="smid", query_en="Aeroports de Paris ADP", query_fr="Groupe ADP"),
    _eu("BOL.PA", "Bolloré", "XPAR", segment="smid", query_en="Bollore"),
    _eu("COFA.PA", "Coface", "XPAR", segment="smid"),
    _eu("SCR.PA", "SCOR", "XPAR", segment="smid", query_en="SCOR reinsurance", query_fr="SCOR réassureur"),
    _eu("ERA.PA", "Eramet", "XPAR", segment="smid"),
    _eu("OVH.PA", "OVHcloud", "XPAR", segment="smid"),
    _eu("SOI.PA", "Soitec", "XPAR", segment="smid"),
    _eu("AYV.PA", "Ayvens", "XPAR", segment="smid"),
    _eu("FDJ.PA", "FDJ United", "XPAR", segment="smid"),
    _eu("DIM.PA", "Sartorius Stedim Biotech", "XPAR", segment="smid"),
    _eu("WLN.PA", "Worldline", "XPAR", segment="smid"),
    _eu("VIRI.PA", "Viridien", "XPAR", segment="smid"),
    _eu("TFI.PA", "TF1", "XPAR", segment="smid", query_en="TF1 group"),
    _eu("VRLA.PA", "Verallia", "XPAR", segment="smid"),
    _eu("ICAD.PA", "Icade", "XPAR", segment="smid"),
    _eu("PLX.PA", "Pluxee", "XPAR", segment="smid"),
    _eu("ELIOR.PA", "Elior", "XPAR", segment="smid", query_en="Elior Group"),
    _eu("STF.PA", "STEF", "XPAR", segment="smid", query_en="STEF transport"),
    # Germany
    _eu("BAS.DE", "BASF", "XETR"), _eu("BAYN.DE", "Bayer", "XETR"), _eu("BMW.DE", "BMW", "XETR"),
    _eu("VOW3.DE", "Volkswagen", "XETR"), _eu("ADS.DE", "Adidas", "XETR"), _eu("IFX.DE", "Infineon", "XETR"),
    _eu("MUV2.DE", "Munich Re", "XETR"), _eu("DBK.DE", "Deutsche Bank", "XETR"), _eu("DB1.DE", "Deutsche Börse", "XETR", query_en="Deutsche Boerse"),
    _eu("RHM.DE", "Rheinmetall", "XETR"), _eu("EOAN.DE", "E.ON", "XETR"), _eu("RWE.DE", "RWE", "XETR"),
    _eu("HEI.DE", "Heidelberg Materials", "XETR"), _eu("MTX.DE", "MTU Aero Engines", "XETR"), _eu("DHL.DE", "DHL Group", "XETR"),
    _eu("VNA.DE", "Vonovia", "XETR"), _eu("SHL.DE", "Siemens Healthineers", "XETR"), _eu("ENR.DE", "Siemens Energy", "XETR"),
    # Netherlands / Belgium
    _eu("ADYEN.AS", "Adyen", "XAMS"), _eu("PRX.AS", "Prosus", "XAMS"), _eu("HEIA.AS", "Heineken", "XAMS"),
    _eu("PHIA.AS", "Philips", "XAMS", query_en="Koninklijke Philips"), _eu("WKL.AS", "Wolters Kluwer", "XAMS"),
    _eu("AD.AS", "Ahold Delhaize", "XAMS"), _eu("ASM.AS", "ASM International", "XAMS"), _eu("AKZA.AS", "Akzo Nobel", "XAMS"),
    _eu("ABI.BR", "AB InBev", "XBRU", query_en="Anheuser-Busch InBev"), _eu("KBC.BR", "KBC Group", "XBRU"),
    _eu("UCB.BR", "UCB", "XBRU", query_en="UCB pharma"), _eu("SOLB.BR", "Solvay", "XBRU", segment="smid"),
    _eu("ACKB.BR", "Ackermans & van Haaren", "XBRU", segment="smid"),
    # Italy / Spain / Portugal
    _eu("UCG.MI", "UniCredit", "XMIL"), _eu("G.MI", "Generali", "XMIL", query_en="Assicurazioni Generali"), _eu("ENI.MI", "Eni", "XMIL", query_en="Eni SpA"),
    _eu("PRY.MI", "Prysmian", "XMIL"), _eu("MONC.MI", "Moncler", "XMIL"), _eu("LDO.MI", "Leonardo", "XMIL", query_en="Leonardo SpA"),
    _eu("CPR.MI", "Campari", "XMIL", segment="smid"), _eu("PST.MI", "Poste Italiane", "XMIL"),
    _eu("TEF.MC", "Telefónica", "XMAD", query_en="Telefonica"), _eu("BBVA.MC", "BBVA", "XMAD"), _eu("CABK.MC", "CaixaBank", "XMAD"),
    _eu("REP.MC", "Repsol", "XMAD"), _eu("AENA.MC", "Aena", "XMAD"), _eu("FER.MC", "Ferrovial", "XMAD"),
    _eu("AMS.MC", "Amadeus", "XMAD", query_en="Amadeus IT"), _eu("GRF.MC", "Grifols", "XMAD", segment="smid"),
    _eu("EDP.LS", "EDP", "XLIS", query_en="EDP Energias de Portugal"), _eu("GALP.LS", "Galp", "XLIS", query_en="Galp Energia"),
    _eu("JMT.LS", "Jerónimo Martins", "XLIS", query_en="Jeronimo Martins"),
    # Switzerland
    _eu("UBSG.SW", "UBS", "XSWX", query_en="UBS Group"), _eu("ZURN.SW", "Zurich Insurance", "XSWX"), _eu("ABBN.SW", "ABB", "XSWX", query_en="ABB Ltd"),
    _eu("CFR.SW", "Richemont", "XSWX"), _eu("LONN.SW", "Lonza", "XSWX"), _eu("SIKA.SW", "Sika", "XSWX", query_en="Sika AG"),
    _eu("HOLN.SW", "Holcim", "XSWX"), _eu("GIVN.SW", "Givaudan", "XSWX"), _eu("GEBN.SW", "Geberit", "XSWX"),
    _eu("SREN.SW", "Swiss Re", "XSWX"),
    # United Kingdom
    _eu("BP.L", "BP", "XLON", query_en="BP plc"), _eu("GSK.L", "GSK", "XLON", query_en="GSK plc"), _eu("RIO.L", "Rio Tinto", "XLON"),
    _eu("BATS.L", "British American Tobacco", "XLON"), _eu("DGE.L", "Diageo", "XLON"), _eu("REL.L", "RELX", "XLON"),
    _eu("LSEG.L", "London Stock Exchange Group", "XLON"), _eu("BARC.L", "Barclays", "XLON"), _eu("LLOY.L", "Lloyds Banking Group", "XLON"),
    _eu("RR.L", "Rolls-Royce", "XLON", query_en="Rolls-Royce Holdings"), _eu("BA.L", "BAE Systems", "XLON"), _eu("GLEN.L", "Glencore", "XLON"),
    _eu("TSCO.L", "Tesco", "XLON"), _eu("NG.L", "National Grid", "XLON"),
    # Nordics
    _eu("VOLV-B.ST", "Volvo", "XSTO", query_en="AB Volvo"), _eu("ATCO-A.ST", "Atlas Copco", "XSTO"), _eu("ERIC-B.ST", "Ericsson", "XSTO"),
    _eu("INVE-B.ST", "Investor AB", "XSTO"), _eu("HM-B.ST", "H&M", "XSTO", query_en="H&M Hennes Mauritz"), _eu("ASSA-B.ST", "Assa Abloy", "XSTO"),
    _eu("EQNR.OL", "Equinor", "XOSL"), _eu("DNB.OL", "DNB Bank", "XOSL"), _eu("NHY.OL", "Norsk Hydro", "XOSL"), _eu("MOWI.OL", "Mowi", "XOSL"),
    _eu("NOKIA.HE", "Nokia", "XHEL"), _eu("NESTE.HE", "Neste", "XHEL"), _eu("KNEBV.HE", "Kone", "XHEL"), _eu("SAMPO.HE", "Sampo", "XHEL"),
    _eu("MAERSK-B.CO", "A.P. Moller-Maersk", "XCSE", query_en="Maersk"), _eu("DSV.CO", "DSV", "XCSE", query_en="DSV logistics"),
    _eu("ORSTED.CO", "Ørsted", "XCSE", query_en="Orsted"), _eu("CARL-B.CO", "Carlsberg", "XCSE"), _eu("VWS.CO", "Vestas", "XCSE"),
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
    # broad / mid & small cap indices
    _t("^STOXX", "STOXX Europe 600", "EU", "XETR", kind="index", segment="broad"),
    _t("^SBF120", "SBF 120", "EU", "XPAR", kind="index", segment="broad"),
    _t("^MDAXI", "MDAX", "EU", "XETR", kind="index", segment="smid"),
    _t("^SDAXI", "SDAX", "EU", "XETR", kind="index", segment="smid"),
    _t("^FTMC", "FTSE 250", "EU", "XLON", kind="index", segment="smid"),
]

FX_COMMOD = [
    _t("EURUSD=X", "EUR/USD", "EU", "XLON", kind="fx"),
    _t("BZ=F", "Brent", "US", "XNYS", kind="commodity"),
    _t("GC=F", "Gold", "US", "XNYS", kind="commodity"),
    # EUR crosses: displayed, and used to convert market caps and financials into EUR (COMPS, EQS)
    _t("EURGBP=X", "EUR/GBP", "EU", "XLON", kind="fx"),
    _t("EURCHF=X", "EUR/CHF", "EU", "XLON", kind="fx"),
    _t("EURSEK=X", "EUR/SEK", "EU", "XLON", kind="fx"),
    _t("EURNOK=X", "EUR/NOK", "EU", "XLON", kind="fx"),
    _t("EURDKK=X", "EUR/DKK", "EU", "XLON", kind="fx"),
]

UNIVERSE = US_WATCH + US_OVERVIEW_EXTRA + EU_WATCH + EU_SMID + EU_MORE + EU_INDICES + FX_COMMOD

# Other names people type in the command bar (search helper on the site). Not data.
ALIASES = {
    "GOOGL": ["Google"], "META": ["Facebook"], "JPM": ["JP Morgan"], "SPY": ["S&P 500", "SP500"],
    "QQQ": ["Nasdaq 100", "Nasdaq"], "DIA": ["Dow Jones"], "IWM": ["Russell 2000"], "^VIX": ["VIX"],
    "MC.PA": ["Moet Hennessy Louis Vuitton"], "TTE.PA": ["Total", "Total Energies"], "RMS.PA": ["Hermes International"],
    "SU.PA": ["Schneider"], "NOVO-B.CO": ["Novo"], "SAN.MC": ["Santander"], "ISP.MI": ["Intesa"],
    "SK.PA": ["Groupe SEB"], "GTT.PA": ["GTT"], "BESI.AS": ["Besi"], "ALLDL.PA": ["LDLC"], "LACR.PA": ["Lacroix"],
    "^FCHI": ["CAC"], "^GDAXI": ["DAX 40"], "^STOXX50E": ["Eurostoxx", "SX5E"], "^STOXX": ["Stoxx 600", "SXXP"],
    "^SBF120": ["SBF"], "^FTSE": ["Footsie"], "EURUSD=X": ["EURUSD", "Euro dollar"],
    "BZ=F": ["Petrole", "Oil", "Brent crude"], "GC=F": ["Or", "Gold"],
}
for _u in UNIVERSE:
    _u["aliases"] = ALIASES.get(_u["ticker"], [])
BY_TICKER = {t["ticker"]: t for t in UNIVERSE}

# Tickers a visitor can put in the watchlist (risk metrics are computed for these)
WATCHLIST_UNIVERSE = [t["ticker"] for t in US_WATCH + EU_WATCH + EU_SMID + EU_MORE]
EU_STOCKS = EU_WATCH + EU_SMID + EU_MORE
# news every hour for these; small & mid caps only in the 08:30 and 17:40 runs (Google rate limits)
NEWS_HOURLY = [t["ticker"] for t in US_WATCH + EU_WATCH]
DEFAULT_WATCHLIST = [t["ticker"] for t in US_WATCH] + ["MC.PA", "ASML.AS", "SAP.DE"]

BENCHMARK = {"US": "SPY", "EU": "^STOXX50E", "EU_SMID": "^STOXX"}


def benchmark_for(info):
    """SPY for US; Euro Stoxx 50 for European large caps; STOXX Europe 600 (broader, includes mid caps)
    for European small & mid caps, whose beta against 50 mega caps is not meaningful."""
    if info["region"] == "US":
        return BENCHMARK["US"]
    return BENCHMARK["EU_SMID"] if info.get("segment") == "smid" else BENCHMARK["EU"]
RISK_FREE_SERIES = {"US": "DGS3MO", "EU": "ECBDFR"}

# Expected quote currency per exchange suffix (used to label prices and to
# detect London quotes in pence). Yahoo's own currency field wins when present.
SUFFIX_CURRENCY = {".PA": "EUR", ".DE": "EUR", ".AS": "EUR", ".MC": "EUR", ".MI": "EUR",
                   ".SW": "CHF", ".L": "GBp", ".CO": "DKK", ".BR": "EUR", ".ST": "SEK", ".OL": "NOK",
                   ".HE": "EUR", ".LS": "EUR"}

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


# Company pages (Yahoo) and ESEF reports are refreshed by rotation in the 08:30 / 17:40 runs
COMPANY_PER_RUN = 80          # ~5 Yahoo calls each
COMPANY_MAX_AGE_H = 20        # a company page younger than this is not refetched
ESEF_PER_RUN = 25
ESEF_MAX_AGE_DAYS = 30        # annual reports change once a year
# Manual fixes for the ESEF name search: {ticker: {"search": "...", "lei": "..."}}
ESEF_OVERRIDES = {
    "MC.PA": {"search": "LVMH"}, "SK.PA": {"search": "SEB S.A"}, "OR.PA": {"search": "L'OREAL"},
    "RMS.PA": {"search": "HERMES INTERNATIONAL"}, "ORA.PA": {"search": "ORANGE"}, "EN.PA": {"search": "BOUYGUES"},
    "CS.PA": {"search": "AXA"}, "DG.PA": {"search": "VINCI"}, "AI.PA": {"search": "AIR LIQUIDE"},
}

FINBERT_MODEL = "ProsusAI/finbert"
TRANSLATE_MODEL = "Helsinki-NLP/opus-mt-tc-big-en-fr"   # open-source EN->FR machine translation (larger, more accurate), CPU
TRANSLATE_BUDGET_S = 600   # max translation time per run; the rest is translated in the next runs

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
