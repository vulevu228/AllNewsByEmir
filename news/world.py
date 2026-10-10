"""
World news for All News by Emir: feeds, topic tags and region detection.

Every story gets
  tags    topics it belongs to: the feed's own topics + keyword topics (war, diseases, ...)
  region  na / sa / eu / af / me / as / oc, from the feed or from the first country
          (or city / leader) named in the title, else the summary; None = global / unknown

Removing a topic = delete its feeds here, its KEYWORD_TAGS entry and its TOPICS row in
site/index.html.
"""

import re

# (name, topics, url, region). region None = work it out per story.
WORLD_FEEDS = [
    # world
    ("BBC World", ["world"], "https://feeds.bbci.co.uk/news/world/rss.xml", None),
    ("Al Jazeera", ["world"], "https://www.aljazeera.com/xml/rss/all.xml", None),
    ("Guardian World", ["world"], "https://www.theguardian.com/world/rss", None),
    ("NPR World", ["world"], "https://feeds.npr.org/1004/rss.xml", None),
    ("DW", ["world"], "https://rss.dw.com/rdf/rss-en-all", None),
    ("France 24", ["world"], "https://www.france24.com/en/rss", None),
    ("UN News", ["world"], "https://news.un.org/feed/subscribe/en/news/all/rss.xml", None),
    ("NYT World", ["world"], "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", None),
    ("Sky News World", ["world"], "https://feeds.skynews.com/feeds/rss/world.xml", None),
    ("CBS World", ["world"], "https://www.cbsnews.com/latest/rss/world", None),
    ("ABC News Intl", ["world"], "https://abcnews.go.com/abcnews/internationalheadlines", None),
    ("BNO News", ["world"], "https://bnonews.com/index.php/feed/", None),
    # North America
    ("BBC US & Canada", ["world"], "https://feeds.bbci.co.uk/news/world/us_and_canada/rss.xml", "na"),
    ("NPR National", ["world"], "https://feeds.npr.org/1003/rss.xml", "na"),
    ("CBC Canada", ["world"], "https://www.cbc.ca/webfeed/rss/rss-canada", "na"),
    ("Mexico News Daily", ["world"], "https://mexiconewsdaily.com/feed/", "na"),
    ("PBS NewsHour", ["world"], "https://www.pbs.org/newshour/feeds/rss/headlines", "na"),
    # South America
    ("BBC Latin America", ["world"], "https://feeds.bbci.co.uk/news/world/latin_america/rss.xml", "sa"),
    ("MercoPress", ["world"], "https://en.mercopress.com/rss", "sa"),
    ("Buenos Aires Times", ["world"], "https://www.batimes.com.ar/feed", "sa"),
    ("Rio Times", ["world"], "https://www.riotimesonline.com/feed/", "sa"),
    ("Colombia One", ["world"], "https://colombiaone.com/feed/", "sa"),
    ("Guardian Americas", ["world"], "https://www.theguardian.com/world/americas/rss", None),
    # Europe
    ("BBC Europe", ["world"], "https://feeds.bbci.co.uk/news/world/europe/rss.xml", "eu"),
    ("Euronews", ["world"], "https://www.euronews.com/rss?level=theme&name=news", "eu"),
    ("Guardian Europe", ["world"], "https://www.theguardian.com/world/europe-news/rss", "eu"),
    ("Politico Europe", ["world", "politics"], "https://www.politico.eu/feed/", "eu"),
    ("The Local Germany", ["world"], "https://feeds.thelocal.com/rss/de", "eu"),
    ("Kyiv Independent", ["world", "war"], "https://kyivindependent.com/news-archive/rss/", "eu"),
    # Africa
    ("BBC Africa", ["world"], "https://feeds.bbci.co.uk/news/world/africa/rss.xml", "af"),
    ("AllAfrica", ["world"], "https://allafrica.com/tools/headlines/rdf/latest/headlines.rdf", "af"),
    ("Guardian Africa", ["world"], "https://www.theguardian.com/world/africa/rss", "af"),
    ("Africanews", ["world"], "https://www.africanews.com/feed/rss", "af"),
    ("Premium Times", ["world"], "https://www.premiumtimesng.com/feed", "af"),
    ("Daily Maverick", ["world"], "https://www.dailymaverick.co.za/dmrss/", "af"),
    # Middle East
    ("BBC Middle East", ["world"], "https://feeds.bbci.co.uk/news/world/middle_east/rss.xml", "me"),
    ("Guardian Middle East", ["world"], "https://www.theguardian.com/world/middleeast/rss", "me"),
    ("Middle East Eye", ["world"], "https://www.middleeasteye.net/rss", "me"),
    ("Al-Monitor", ["world"], "https://www.al-monitor.com/rss", "me"),
    # Asia
    ("BBC Asia", ["world"], "https://feeds.bbci.co.uk/news/world/asia/rss.xml", "as"),
    ("SCMP", ["world"], "https://www.scmp.com/rss/91/feed", "as"),
    ("The Diplomat", ["world"], "https://thediplomat.com/feed/", "as"),
    ("CNA", ["world"], "https://www.channelnewsasia.com/api/v1/rss-outbound-feed?_format=xml", "as"),
    ("Japan Times", ["world"], "https://www.japantimes.co.jp/feed/", "as"),
    ("Times of India", ["world"], "https://timesofindia.indiatimes.com/rssfeedstopstories.cms", "as"),
    ("Yonhap", ["world"], "https://en.yna.co.kr/RSS/news.xml", "as"),
    ("The Hindu World", ["world"], "https://www.thehindu.com/news/international/feeder/default.rss", None),
    # Oceania
    ("ABC Australia", ["world"], "https://www.abc.net.au/news/feed/51120/rss.xml", "oc"),
    ("RNZ", ["world"], "https://www.rnz.co.nz/rss/national.xml", "oc"),
    ("RNZ Pacific", ["world"], "https://www.rnz.co.nz/rss/pacific.xml", "oc"),
    ("Guardian Australia", ["world"], "https://www.theguardian.com/australia-news/rss", "oc"),
    ("BBC Australia", ["world"], "https://feeds.bbci.co.uk/news/world/australia/rss.xml", "oc"),
    # nature
    ("Guardian Environment", ["nature"], "https://www.theguardian.com/environment/rss", None),
    ("Guardian Wildlife", ["nature"], "https://www.theguardian.com/environment/wildlife/rss", None),
    ("BBC Science & Environment", ["nature", "science"], "https://feeds.bbci.co.uk/news/science_and_environment/rss.xml", None),
    ("Mongabay", ["nature"], "https://news.mongabay.com/feed/", None),
    ("ScienceDaily Earth", ["nature"], "https://www.sciencedaily.com/rss/earth_climate.xml", None),
    ("ScienceDaily Wildlife", ["nature"], "https://www.sciencedaily.com/rss/plants_animals.xml", None),
    ("Inside Climate News", ["nature"], "https://insideclimatenews.org/feed/", None),
    ("Carbon Brief", ["nature", "energy"], "https://www.carbonbrief.org/feed/", None),
    # war
    ("War on the Rocks", ["war"], "https://warontherocks.com/feed/", None),
    ("Breaking Defense", ["war"], "https://breakingdefense.com/feed/", None),
    ("The War Zone", ["war"], "https://www.twz.com/feed", None),
    ("Defense One", ["war"], "https://www.defenseone.com/rss/all/", None),
    ("Guardian Ukraine", ["war", "world"], "https://www.theguardian.com/world/ukraine/rss", "eu"),
    ("Guardian Military", ["war"], "https://www.theguardian.com/uk/military/rss", None),
    ("UN Peace & Security", ["war"], "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml", None),
    ("Crisis Group", ["war"], "https://www.crisisgroup.org/rss.xml", None),
    # economy
    ("Guardian Business", ["economy"], "https://www.theguardian.com/business/rss", None),
    ("BBC Business", ["economy"], "https://feeds.bbci.co.uk/news/business/rss.xml", None),
    ("CNBC World", ["economy"], "https://www.cnbc.com/id/100727362/device/rss/rss.html", None),
    ("CNBC Economy", ["economy"], "https://www.cnbc.com/id/20910258/device/rss/rss.html", None),
    ("MarketWatch", ["economy"], "https://feeds.content.dowjones.io/public/rss/mw_topstories", None),
    ("NPR Economy", ["economy"], "https://feeds.npr.org/1017/rss.xml", "na"),
    # industry
    ("Supply Chain Dive", ["industry"], "https://www.supplychaindive.com/feeds/news/", None),
    ("Manufacturing Dive", ["industry"], "https://www.manufacturingdive.com/feeds/news/", None),
    ("Construction Dive", ["industry"], "https://www.constructiondive.com/feeds/news/", None),
    ("FreightWaves", ["industry"], "https://www.freightwaves.com/news/feed", None),
    ("gCaptain", ["industry"], "https://gcaptain.com/feed/", None),
    ("Splash247", ["industry"], "https://splash247.com/feed/", None),
    ("Mining.com", ["industry"], "https://www.mining.com/feed/", None),
    ("The Robot Report", ["industry", "tech"], "https://www.therobotreport.com/feed/", None),
    ("Electrek", ["industry", "energy"], "https://electrek.co/feed/", None),
    # health
    ("BBC Health", ["health"], "https://feeds.bbci.co.uk/news/health/rss.xml", None),
    ("Guardian Health", ["health"], "https://www.theguardian.com/society/health/rss", None),
    ("NPR Health", ["health"], "https://feeds.npr.org/1128/rss.xml", None),
    ("STAT", ["health"], "https://www.statnews.com/feed/", None),
    ("Medical Xpress", ["health"], "https://medicalxpress.com/rss-feed/", None),
    # diseases
    ("Avian Flu Diary", ["diseases"], "https://afludiary.blogspot.com/feeds/posts/default?alt=rss", None),
    ("ECDC Threats", ["diseases", "health"], "https://www.ecdc.europa.eu/en/taxonomy/term/1244/feed", "eu"),
    ("Medical Xpress Infectious", ["diseases", "health"], "https://medicalxpress.com/rss-feed/infectious-diseases-news/", None),
    ("ScienceDaily Infectious", ["diseases", "health"], "https://www.sciencedaily.com/rss/health_medicine/infectious_diseases.xml", None),
    ("Guardian Global Health", ["health"], "https://www.theguardian.com/global-development/global-health/rss", None),
    # fun
    ("UPI Odd News", ["fun"], "https://rss.upi.com/news/odd_news.rss", None),
    ("Good News Network", ["fun"], "https://www.goodnewsnetwork.org/feed/", None),
    ("Positive News", ["fun"], "https://www.positive.news/feed/", None),
    ("Reasons to be Cheerful", ["fun"], "https://reasonstobecheerful.world/feed/", None),
    ("Atlas Obscura", ["fun"], "https://www.atlasobscura.com/feeds/latest", None),
    ("Mental Floss", ["fun"], "https://www.mentalfloss.com/rss.xml", None),
    ("Smithsonian Smart News", ["fun", "science"], "https://www.smithsonianmag.com/rss/smart-news/", None),
    # extra topics
    ("ScienceDaily", ["science"], "https://www.sciencedaily.com/rss/top/science.xml", None),
    ("Phys.org", ["science"], "https://phys.org/rss-feed/", None),
    ("Guardian Science", ["science"], "https://www.theguardian.com/science/rss", None),
    ("NASA", ["space"], "https://www.nasa.gov/news-release/feed/", None),
    ("SpaceNews", ["space"], "https://spacenews.com/feed/", None),
    ("Spaceflight Now", ["space"], "https://spaceflightnow.com/feed/", None),
    ("ESA", ["space"], "https://www.esa.int/rssfeed/Our_Activities/Space_News", None),
    ("Universe Today", ["space"], "https://www.universetoday.com/feed/", None),
    ("Ars Technica (all)", ["tech"], "https://feeds.arstechnica.com/arstechnica/index", None),
    ("The Verge (all)", ["tech"], "https://www.theverge.com/rss/index.xml", None),
    ("BBC Technology", ["tech"], "https://feeds.bbci.co.uk/news/technology/rss.xml", None),
    ("GDACS", ["disasters"], "https://www.gdacs.org/xml/rss.xml", None),
    ("USGS Earthquakes", ["disasters"], "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/significant_week.atom", None),
    ("Guardian Energy", ["energy"], "https://www.theguardian.com/environment/energy/rss", None),
    ("Utility Dive", ["energy"], "https://www.utilitydive.com/feeds/news/", None),
    ("OilPrice", ["energy", "economy"], "https://oilprice.com/rss/main", None),
    ("Politico US", ["politics"], "https://rss.politico.com/congress.xml", "na"),  # politics-news.xml retired (404, Sep 2026)
    ("Guardian Politics", ["politics"], "https://www.theguardian.com/politics/rss", "eu"),
]

# topics added to any story (world or AI feed) whose title/summary matches
_KW = {
    "war": r"wars?|warfare|war-torn|troops?|missiles?|air ?strikes?|drones?|drone (?:strike|attack)s?|shelling|shelled|"
           r"mobili[sz]ation|land ?mines?|ceasefire|"
           r"cease-fire|invasion|invaded|insurgen\w+|militants?|militias?|armed forces|front ?line|bombardment|"
           r"artillery|hostages?|rebels?|coup|genocide|military|soldiers|jihadists?|Hamas|Hezbollah|Houthis?|"
           r"(?:killed|wounded) in (?:an? )?(?:attack|strike|raid)s?",
    "diseases": r"outbreaks?|epidemics?|pandemics?|bird flu|avian (?:flu|influenza)|H5N\d|H7N\d|measles|cholera|"
                r"ebola|mpox|monkeypox|dengue|malaria|tuberculosis|polio|covid(?:-19)?|coronavirus|zika|marburg|"
                r"nipah|meningitis|typhoid|yellow fever|rabies|HIV|hepatitis|plague|norovirus|salmonella|"
                r"listeria|E\. coli|chikungunya|diphtheria|whooping cough|pertussis|anthrax|infectious disease",
    "disasters": r"earthquakes?|quake|tsunamis?|hurricanes?|typhoons?|cyclones?|tornado(?:es)?|floods?|flooding|"
                 r"flash floods?|wildfires?|bushfires?|forest fires?|landslides?|mudslides?|volcan\w+|eruptions?|"
                 r"droughts?|heatwaves?|heat wave|avalanches?|storm surge",
    "economy": r"inflation|interest rates?|central bank|GDP|recession|tariffs?|stock markets?|Wall Street|"
               r"bond yields?|unemployment|jobs report|trade (?:deal|war)|IMF|World Bank|economy|economic|"
               r"Federal Reserve|ECB|jobs|job creation|exports?|imports?|trade|budget deficit|growth forecast",
    "space": r"NASA|SpaceX|rocket launch|astronauts?|spacecraft|space station|Artemis|telescope|asteroid",
    "energy": r"oil prices?|OPEC|natural gas|LNG|renewables?|solar power|wind (?:power|farm)s?|nuclear power|"
              r"power grid|electricity prices?|blackouts?",
    "nature": r"wildlife|endangered|species|biodiversity|deforestation|coral reefs?|climate change|global warming",
}
KEYWORD_TAGS = {t: re.compile(rf"(?i)\b(?:{p})\b") for t, p in _KW.items()}
# case-sensitive short words that would false-match in lower case
KEYWORD_TAGS_CS = {"war": re.compile(r"\bNATO\b"), "diseases": re.compile(r"\bWHO\b")}

# first place named wins; title before summary
_PLACES = {
    "na": r"United States|U\.S\.|US|USA|American?s?|Americans|Washington|White House|Pentagon|Congress|Senate|"
          r"Trump|Biden|Vance|New York|California|Texas|Florida|Chicago|Los Angeles|Canada|Canadian|Ottawa|"
          r"Toronto|Carney|Mexico|Mexican|Sheinbaum|Cuba|Cuban|Haiti|Haitian|Guatemala|Honduras|El Salvador|"
          r"Nicaragua|Costa Rica|Panama|Jamaica|Puerto Rico|Dominican Republic|Greenland",
    "sa": r"Brazil|Brazilian|Lula|Argentina|Argentine|Milei|Chile|Chilean|Colombia|Colombian|Peru|Peruvian|"
          r"Venezuela|Venezuelan|Maduro|Ecuador|Bolivia|Paraguay|Uruguay|Guyana|Suriname|Latin America|"
          r"South America|Sao Paulo|São Paulo|Rio de Janeiro|Buenos Aires|Bogota|Bogotá|Caracas|Lima|Santiago",
    "eu": r"Europe|European|EU|Brussels|Britain|British|UK|England|Scotland|Wales|London|Starmer|Ireland|Irish|"
          r"France|French|Paris|Macron|Germany|German|Berlin|Merz|Italy|Italian|Rome|Meloni|Spain|Spanish|Madrid|"
          r"Portugal|Netherlands|Dutch|Belgium|Belgian|Switzerland|Swiss|Austria|Poland|Polish|Warsaw|Czech|"
          r"Slovakia|Hungary|Hungarian|Orban|Orbán|Romania|Bulgaria|Greece|Greek|Athens|Serbia|Croatia|Bosnia|"
          r"Kosovo|Albania|Moldova|Ukraine|Ukrainian|Kyiv|Kiev|Zelensky[iy]?|Russia|Russian|Moscow|Kremlin|Putin|"
          r"Belarus|Lithuania|Latvia|Estonia|Finland|Finnish|Sweden|Swedish|Norway|Norwegian|Denmark|Danish|"
          r"Iceland|Hamburg|Munich",
    "af": r"Africa|African|Nigeria|Nigerian|Lagos|Abuja|Kenya|Kenyan|Nairobi|Ethiopia|Ethiopian|Egypt|Egyptian|"
          r"Cairo|South Africa|Johannesburg|Cape Town|Ghana|Sudan|Sudanese|Khartoum|Darfur|South Sudan|Somalia|"
          r"Somali|Congo|Congolese|DRC|Kinshasa|Uganda|Tanzania|Rwanda|Burundi|Morocco|Moroccan|Algeria|Tunisia|"
          r"Libya|Libyan|Mali|Malian|Niger|Burkina Faso|Senegal|Cameroon|Zimbabwe|Zambia|Mozambique|Angola|"
          r"Namibia|Botswana|Madagascar|Malawi|Sahel|Eritrea|Ivory Coast|Côte d'Ivoire|Sierra Leone|Liberia",
    "me": r"Middle East|Israel|Israeli|Netanyahu|Gaza|Gazans?|West Bank|Palestin\w+|Jerusalem|Tel Aviv|Hamas|"
          r"Hezbollah|Lebanon|Lebanese|Beirut|Syria|Syrian|Damascus|Iran|Iranian|Tehran|Iraq|Iraqi|Baghdad|"
          r"Yemen|Yemeni|Houthis?|Saudi|Riyadh|UAE|Emirati|Dubai|Abu Dhabi|Qatar|Qatari|Doha|Kuwait|Oman|"
          r"Bahrain|Jordanian|Amman|Turkey|Türkiye|Turkish|Ankara|Istanbul|Erdogan|Erdoğan|Kurdish|Kurds",
    "as": r"Asia|Asian|China|Chinese|Beijing|Shanghai|Xi Jinping|Hong Kong|Taiwan|Taiwanese|Taipei|Japan|"
          r"Japanese|Tokyo|Korea|Korean|Seoul|Pyongyang|Kim Jong|India|Indian|Delhi|Mumbai|Modi|Pakistan|"
          r"Pakistani|Islamabad|Afghanistan|Afghan|Taliban|Bangladesh|Dhaka|Sri Lanka|Nepal|Myanmar|Burma|"
          r"Thailand|Thai|Bangkok|Vietnam|Vietnamese|Cambodia|Laos|Malaysia|Singapore|Indonesia|Indonesian|"
          r"Jakarta|Philippines|Philippine|Filipino|Manila|Mongolia|Kazakhstan|Uzbekistan|Kyrgyzstan|"
          r"Tajikistan|Turkmenistan",
    "oc": r"Australia|Australian|Sydney|Melbourne|Canberra|Brisbane|Perth|Albanese|New Zealand|Auckland|"
          r"Wellington|Fiji|Samoa|Tonga|Papua New Guinea|Solomon Islands|Vanuatu|Pacific Islands?",
}
_PLACE_RE = [(r, re.compile(rf"\b(?:{p})\b")) for r, p in _PLACES.items()]


def detect_region(title, summary):
    for text in (title, summary):
        best = None
        for region, rx in _PLACE_RE:
            m = rx.search(text or "")
            if m and (best is None or m.start() < best[0]):
                best = (m.start(), region)
        if best:
            return best[1]
    return None


def keyword_tags(text):
    tags = {t for t, rx in KEYWORD_TAGS.items() if rx.search(text)}
    tags |= {t for t, rx in KEYWORD_TAGS_CS.items() if rx.search(text)}
    return tags


def keep_entry(feed_name, entry):
    """Per-feed filters for noisy feeds."""
    if feed_name == "GDACS":  # green alerts are minor events - keep orange / red only
        return entry.get("gdacs_alertlevel") in ("Orange", "Red")
    return True


# ---------------------------------------------------------------- confidence
# How sure a story belongs to each of its topics and to its region (0-1). Topics and regions below
# CONFIDENCE are dropped from the story (it still shows under All / Everywhere):
#   topic from the feed itself (a war feed's story is war news)                      1.0
#   keyword topic: named in the title 0.75, only in the summary 0.6, +0.1 per further
#   distinct keyword (up to +0.2); "war" used as a metaphor (trade war, Star Wars...) -0.3
#   region from a regional feed 1.0; first place in the title 0.85 (0.75 when the title
#   names places in several regions); only in the summary 0.6, or 0.75 with 2+ mentions
CONFIDENCE = 0.70
_METAPHOR = re.compile(r"(?i)\b(?:trade|culture|price|bidding|talent|turf|tariff|currency|console|streaming|format|"
                       r"star|cola|flame|console) wars?\b|\bwar (?:on (?:drugs|poverty|cancer|waste|christmas|woke)|"
                       r"of words|room|chest|games?|horse|paint)\b|\bwarfare (?:game|genre)|\bcall of duty")


def _matches(rx, text):
    return {m.group(0).lower() for m in rx.finditer(text or "")}


def topic_confidence(tag, title, summary, feed_tags):
    if tag in feed_tags:
        return 1.0
    rx = KEYWORD_TAGS.get(tag)
    if rx is None:
        return 1.0  # "ai" and other non-keyword tags keep their own rules
    in_title, in_all = _matches(rx, title), _matches(rx, f"{title} {summary}")
    cs = KEYWORD_TAGS_CS.get(tag)
    if cs:
        in_title |= _matches(cs, title)
        in_all |= _matches(cs, f"{title} {summary}")
    if not in_all:
        return 0.0
    c = (0.75 if in_title else 0.6) + min(0.1 * (len(in_all) - 1), 0.2)
    if tag == "war" and _METAPHOR.search(f"{title} {summary}"):
        c -= 0.3
    return round(min(c, 1.0), 2)


def region_confidence(region, title, summary, feed_region):
    if not region:
        return 0.0
    if feed_region:
        return 1.0
    rx = dict(_PLACE_RE)[region]
    if rx.search(title or ""):
        others = {r for r, x in _PLACE_RE if r != region and x.search(title or "")}
        return 0.75 if others else 0.85
    return 0.75 if len({m.group(0) for m in rx.finditer(summary or "")}) >= 2 else 0.6
