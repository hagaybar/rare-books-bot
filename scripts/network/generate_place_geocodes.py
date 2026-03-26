#!/usr/bin/env python3
"""Generate place_geocodes.json for the network map explorer.

Maps normalized place names (place_norm) from the bibliographic database
to lat/lon coordinates. These are well-known historical publishing cities
whose coordinates are stable and well-established.

Usage:
    python -m scripts.network.generate_place_geocodes

If bibliographic.db is available, it queries distinct place_norm values.
Otherwise, it uses the comprehensive built-in mapping covering all known
places in the collection.

Output: data/normalization/place_geocodes.json
"""

import json
import sqlite3
import sys
from pathlib import Path

# Comprehensive geocode mapping for all known place_norm values in the
# rare books bibliographic collection. Coordinates are for the historical
# city centers. Places that are not geocodable (e.g., "[sine loco]",
# "place of publication not identified") are excluded.

PLACE_GEOCODES = {
    # === Major European Publishing Centers ===
    "paris": {"lat": 48.8566, "lon": 2.3522, "display_name": "Paris"},
    "london": {"lat": 51.5074, "lon": -0.1278, "display_name": "London"},
    "amsterdam": {"lat": 52.3676, "lon": 4.9041, "display_name": "Amsterdam"},
    "venice": {"lat": 45.4408, "lon": 12.3155, "display_name": "Venice"},
    "berlin": {"lat": 52.5200, "lon": 13.4050, "display_name": "Berlin"},
    "leipzig": {"lat": 51.3397, "lon": 12.3731, "display_name": "Leipzig"},
    "leiden": {"lat": 52.1601, "lon": 4.4970, "display_name": "Leiden"},
    "frankfurt": {"lat": 50.1109, "lon": 8.6821, "display_name": "Frankfurt"},
    "basel": {"lat": 47.5596, "lon": 7.5886, "display_name": "Basel"},
    "vienna": {"lat": 48.2082, "lon": 16.3738, "display_name": "Vienna"},
    "hamburg": {"lat": 53.5511, "lon": 9.9937, "display_name": "Hamburg"},
    "frankfurt am main": {"lat": 50.1109, "lon": 8.6821, "display_name": "Frankfurt am Main"},
    "munich": {"lat": 48.1351, "lon": 11.5820, "display_name": "Munich"},
    "rome": {"lat": 41.9028, "lon": 12.4964, "display_name": "Rome"},
    "halle": {"lat": 51.4969, "lon": 11.9688, "display_name": "Halle"},
    "mantua": {"lat": 45.1564, "lon": 10.7914, "display_name": "Mantua"},
    "the hague": {"lat": 52.0705, "lon": 4.3007, "display_name": "The Hague"},
    "prague": {"lat": 50.0755, "lon": 14.4378, "display_name": "Prague"},
    "geneva": {"lat": 46.2044, "lon": 6.1432, "display_name": "Geneva"},
    "nuremberg": {"lat": 49.4521, "lon": 11.0767, "display_name": "Nuremberg"},
    "cologne": {"lat": 50.9375, "lon": 6.9603, "display_name": "Cologne"},
    "wittenberg": {"lat": 51.8671, "lon": 12.6484, "display_name": "Wittenberg"},
    "antwerp": {"lat": 51.2194, "lon": 4.4025, "display_name": "Antwerp"},
    "lyon": {"lat": 45.7640, "lon": 4.8357, "display_name": "Lyon"},
    "livorno": {"lat": 43.5485, "lon": 10.3106, "display_name": "Livorno"},
    "strasbourg": {"lat": 48.5734, "lon": 7.7521, "display_name": "Strasbourg"},
    "florence": {"lat": 43.7696, "lon": 11.2558, "display_name": "Florence"},
    "zurich": {"lat": 47.3769, "lon": 8.5417, "display_name": "Zurich"},
    "brussels": {"lat": 50.8503, "lon": 4.3517, "display_name": "Brussels"},
    "madrid": {"lat": 40.4168, "lon": -3.7038, "display_name": "Madrid"},
    "lisbon": {"lat": 38.7223, "lon": -9.1393, "display_name": "Lisbon"},
    "edinburgh": {"lat": 55.9533, "lon": -3.1883, "display_name": "Edinburgh"},
    "oxford": {"lat": 51.7520, "lon": -1.2577, "display_name": "Oxford"},
    "cambridge": {"lat": 52.2053, "lon": 0.1218, "display_name": "Cambridge"},
    "rotterdam": {"lat": 51.9244, "lon": 4.4777, "display_name": "Rotterdam"},
    "utrecht": {"lat": 52.0907, "lon": 5.1214, "display_name": "Utrecht"},
    "dresden": {"lat": 51.0504, "lon": 13.7373, "display_name": "Dresden"},
    "stuttgart": {"lat": 48.7758, "lon": 9.1829, "display_name": "Stuttgart"},
    "hannover": {"lat": 52.3759, "lon": 9.7320, "display_name": "Hannover"},
    "hanover": {"lat": 52.3759, "lon": 9.7320, "display_name": "Hanover"},
    "breslau": {"lat": 51.1079, "lon": 17.0385, "display_name": "Breslau (Wroclaw)"},
    "wroclaw": {"lat": 51.1079, "lon": 17.0385, "display_name": "Wroclaw"},
    "konigsberg": {"lat": 54.7104, "lon": 20.4522, "display_name": "Konigsberg (Kaliningrad)"},
    "danzig": {"lat": 54.3520, "lon": 18.6466, "display_name": "Danzig (Gdansk)"},
    "gdansk": {"lat": 54.3520, "lon": 18.6466, "display_name": "Gdansk"},
    "krakow": {"lat": 50.0647, "lon": 19.9450, "display_name": "Krakow"},
    "cracow": {"lat": 50.0647, "lon": 19.9450, "display_name": "Cracow"},
    "warsaw": {"lat": 52.2297, "lon": 21.0122, "display_name": "Warsaw"},
    "budapest": {"lat": 47.4979, "lon": 19.0402, "display_name": "Budapest"},
    "copenhagen": {"lat": 55.6761, "lon": 12.5683, "display_name": "Copenhagen"},
    "stockholm": {"lat": 59.3293, "lon": 18.0686, "display_name": "Stockholm"},
    "naples": {"lat": 40.8518, "lon": 14.2681, "display_name": "Naples"},
    "padua": {"lat": 45.4064, "lon": 11.8768, "display_name": "Padua"},
    "bologna": {"lat": 44.4949, "lon": 11.3426, "display_name": "Bologna"},
    "milan": {"lat": 45.4642, "lon": 9.1900, "display_name": "Milan"},
    "turin": {"lat": 45.0703, "lon": 7.6869, "display_name": "Turin"},
    "genoa": {"lat": 44.4056, "lon": 8.9463, "display_name": "Genoa"},
    "pisa": {"lat": 43.7228, "lon": 10.4017, "display_name": "Pisa"},
    "ferrara": {"lat": 44.8381, "lon": 11.6199, "display_name": "Ferrara"},
    "verona": {"lat": 45.4384, "lon": 10.9916, "display_name": "Verona"},
    "reggio emilia": {"lat": 44.6989, "lon": 10.6310, "display_name": "Reggio Emilia"},
    "cremona": {"lat": 45.1336, "lon": 10.0225, "display_name": "Cremona"},
    "brescia": {"lat": 45.5416, "lon": 10.2118, "display_name": "Brescia"},
    "parma": {"lat": 44.8015, "lon": 10.3279, "display_name": "Parma"},
    "modena": {"lat": 44.6471, "lon": 10.9252, "display_name": "Modena"},
    "perugia": {"lat": 43.1107, "lon": 12.3908, "display_name": "Perugia"},
    "siena": {"lat": 43.3188, "lon": 11.3308, "display_name": "Siena"},
    "palermo": {"lat": 38.1157, "lon": 13.3615, "display_name": "Palermo"},
    "lucca": {"lat": 43.8429, "lon": 10.5027, "display_name": "Lucca"},
    "ravenna": {"lat": 44.4184, "lon": 12.2035, "display_name": "Ravenna"},
    "pesaro": {"lat": 43.9098, "lon": 12.9131, "display_name": "Pesaro"},
    "ancona": {"lat": 43.6158, "lon": 13.5189, "display_name": "Ancona"},
    "sabbioneta": {"lat": 44.9983, "lon": 10.4889, "display_name": "Sabbioneta"},
    "riva di trento": {"lat": 45.8858, "lon": 10.8433, "display_name": "Riva di Trento"},
    "fano": {"lat": 43.8400, "lon": 13.0190, "display_name": "Fano"},
    "soncino": {"lat": 45.4000, "lon": 9.8667, "display_name": "Soncino"},
    "augsburg": {"lat": 48.3705, "lon": 10.8978, "display_name": "Augsburg"},
    "mainz": {"lat": 49.9929, "lon": 8.2473, "display_name": "Mainz"},
    "heidelberg": {"lat": 49.3988, "lon": 8.6724, "display_name": "Heidelberg"},
    "tubingen": {"lat": 48.5216, "lon": 9.0576, "display_name": "Tubingen"},
    "gottingen": {"lat": 51.5328, "lon": 9.9354, "display_name": "Gottingen"},
    "jena": {"lat": 50.9271, "lon": 11.5892, "display_name": "Jena"},
    "marburg": {"lat": 50.8019, "lon": 8.7711, "display_name": "Marburg"},
    "erlangen": {"lat": 49.5897, "lon": 11.0120, "display_name": "Erlangen"},
    "freiburg": {"lat": 47.9990, "lon": 7.8421, "display_name": "Freiburg"},
    "bonn": {"lat": 50.7374, "lon": 7.0982, "display_name": "Bonn"},
    "weimar": {"lat": 50.9795, "lon": 11.3235, "display_name": "Weimar"},
    "rostock": {"lat": 54.0887, "lon": 12.1407, "display_name": "Rostock"},
    "altona": {"lat": 53.5497, "lon": 9.9358, "display_name": "Altona"},
    "offenbach": {"lat": 50.0956, "lon": 8.7761, "display_name": "Offenbach"},
    "frankfurt an der oder": {"lat": 52.3471, "lon": 14.5506, "display_name": "Frankfurt an der Oder"},
    "karlsruhe": {"lat": 49.0069, "lon": 8.4037, "display_name": "Karlsruhe"},
    "darmstadt": {"lat": 49.8728, "lon": 8.6512, "display_name": "Darmstadt"},
    "dessau": {"lat": 51.8355, "lon": 12.2461, "display_name": "Dessau"},
    "wolfenbuttel": {"lat": 52.1633, "lon": 10.5364, "display_name": "Wolfenbuttel"},
    "luneburg": {"lat": 53.2494, "lon": 10.4142, "display_name": "Luneburg"},
    "lubeck": {"lat": 53.8655, "lon": 10.6866, "display_name": "Lubeck"},
    "bamberg": {"lat": 49.8988, "lon": 10.9028, "display_name": "Bamberg"},
    "wurzburg": {"lat": 49.7913, "lon": 9.9534, "display_name": "Wurzburg"},
    "kassel": {"lat": 51.3127, "lon": 9.4797, "display_name": "Kassel"},
    "magdeburg": {"lat": 52.1205, "lon": 11.6276, "display_name": "Magdeburg"},
    "erfurt": {"lat": 50.9787, "lon": 11.0328, "display_name": "Erfurt"},
    "giessen": {"lat": 50.5840, "lon": 8.6784, "display_name": "Giessen"},
    "helmstedt": {"lat": 52.2279, "lon": 11.0099, "display_name": "Helmstedt"},
    "greifswald": {"lat": 54.0865, "lon": 13.3923, "display_name": "Greifswald"},
    "halle an der saale": {"lat": 51.4969, "lon": 11.9688, "display_name": "Halle an der Saale"},
    "bern": {"lat": 46.9480, "lon": 7.4474, "display_name": "Bern"},
    "lausanne": {"lat": 46.5197, "lon": 6.6323, "display_name": "Lausanne"},
    "leeuwarden": {"lat": 53.2012, "lon": 5.7999, "display_name": "Leeuwarden"},
    "groningen": {"lat": 53.2194, "lon": 6.5665, "display_name": "Groningen"},
    "delft": {"lat": 52.0116, "lon": 4.3571, "display_name": "Delft"},
    "haarlem": {"lat": 52.3874, "lon": 4.6462, "display_name": "Haarlem"},
    "deventer": {"lat": 52.2660, "lon": 6.1552, "display_name": "Deventer"},
    "middelburg": {"lat": 51.4988, "lon": 3.6109, "display_name": "Middelburg"},
    "ghent": {"lat": 51.0543, "lon": 3.7174, "display_name": "Ghent"},
    "bruges": {"lat": 51.2093, "lon": 3.2247, "display_name": "Bruges"},
    "louvain": {"lat": 50.8798, "lon": 4.7005, "display_name": "Louvain"},
    "leuven": {"lat": 50.8798, "lon": 4.7005, "display_name": "Leuven"},
    "liege": {"lat": 50.6292, "lon": 5.5797, "display_name": "Liege"},
    "mechelen": {"lat": 51.0259, "lon": 4.4776, "display_name": "Mechelen"},
    "dublin": {"lat": 53.3498, "lon": -6.2603, "display_name": "Dublin"},
    "glasgow": {"lat": 55.8642, "lon": -4.2518, "display_name": "Glasgow"},
    "barcelona": {"lat": 41.3874, "lon": 2.1686, "display_name": "Barcelona"},
    "seville": {"lat": 37.3891, "lon": -5.9845, "display_name": "Seville"},
    "toledo": {"lat": 39.8628, "lon": -4.0273, "display_name": "Toledo"},
    "salamanca": {"lat": 40.9701, "lon": -5.6635, "display_name": "Salamanca"},
    "alcala de henares": {"lat": 40.4819, "lon": -3.3635, "display_name": "Alcala de Henares"},
    "valladolid": {"lat": 41.6523, "lon": -4.7245, "display_name": "Valladolid"},
    "coimbra": {"lat": 40.2033, "lon": -8.4103, "display_name": "Coimbra"},
    "porto": {"lat": 41.1579, "lon": -8.6291, "display_name": "Porto"},
    "bordeaux": {"lat": 44.8378, "lon": -0.5792, "display_name": "Bordeaux"},
    "toulouse": {"lat": 43.6047, "lon": 1.4442, "display_name": "Toulouse"},
    "marseille": {"lat": 43.2965, "lon": 5.3698, "display_name": "Marseille"},
    "rouen": {"lat": 49.4432, "lon": 1.0999, "display_name": "Rouen"},
    "avignon": {"lat": 43.9493, "lon": 4.8055, "display_name": "Avignon"},
    "montpellier": {"lat": 43.6108, "lon": 3.8767, "display_name": "Montpellier"},
    "orleans": {"lat": 47.9029, "lon": 1.9039, "display_name": "Orleans"},
    "metz": {"lat": 49.1193, "lon": 6.1757, "display_name": "Metz"},
    "nancy": {"lat": 48.6921, "lon": 6.1844, "display_name": "Nancy"},
    "dijon": {"lat": 47.3220, "lon": 5.0415, "display_name": "Dijon"},
    "grenoble": {"lat": 45.1885, "lon": 5.7245, "display_name": "Grenoble"},
    "nantes": {"lat": 47.2184, "lon": -1.5536, "display_name": "Nantes"},
    "lille": {"lat": 50.6292, "lon": 3.0573, "display_name": "Lille"},

    # === Middle East / Holy Land ===
    "jerusalem": {"lat": 31.7683, "lon": 35.2137, "display_name": "Jerusalem"},
    "tel aviv": {"lat": 32.0853, "lon": 34.7818, "display_name": "Tel Aviv"},
    "safed": {"lat": 32.9646, "lon": 35.4960, "display_name": "Safed"},
    "constantinople": {"lat": 41.0082, "lon": 28.9784, "display_name": "Constantinople"},
    "istanbul": {"lat": 41.0082, "lon": 28.9784, "display_name": "Istanbul"},
    "izmir": {"lat": 38.4192, "lon": 27.1287, "display_name": "Izmir"},
    "smyrna": {"lat": 38.4192, "lon": 27.1287, "display_name": "Smyrna"},
    "cairo": {"lat": 30.0444, "lon": 31.2357, "display_name": "Cairo"},
    "alexandria": {"lat": 31.2001, "lon": 29.9187, "display_name": "Alexandria"},
    "beirut": {"lat": 33.8938, "lon": 35.5018, "display_name": "Beirut"},
    "damascus": {"lat": 33.5138, "lon": 36.2765, "display_name": "Damascus"},
    "aleppo": {"lat": 36.2021, "lon": 37.1343, "display_name": "Aleppo"},
    "baghdad": {"lat": 33.3152, "lon": 44.3661, "display_name": "Baghdad"},
    "tiberias": {"lat": 32.7940, "lon": 35.5300, "display_name": "Tiberias"},
    "hebron": {"lat": 31.5326, "lon": 35.0998, "display_name": "Hebron"},
    "jaffa": {"lat": 32.0534, "lon": 34.7509, "display_name": "Jaffa"},
    "acre": {"lat": 32.9272, "lon": 35.0761, "display_name": "Acre"},
    "haifa": {"lat": 32.7940, "lon": 34.9896, "display_name": "Haifa"},
    "nablus": {"lat": 32.2211, "lon": 35.2544, "display_name": "Nablus"},
    "gaza": {"lat": 31.5017, "lon": 34.4668, "display_name": "Gaza"},
    "ramla": {"lat": 31.9275, "lon": 34.8651, "display_name": "Ramla"},
    "tunis": {"lat": 36.8065, "lon": 10.1815, "display_name": "Tunis"},
    "fez": {"lat": 34.0181, "lon": -5.0078, "display_name": "Fez"},
    "algiers": {"lat": 36.7538, "lon": 3.0588, "display_name": "Algiers"},
    "tripoli": {"lat": 32.9022, "lon": 13.1802, "display_name": "Tripoli"},
    "salonika": {"lat": 40.6401, "lon": 22.9444, "display_name": "Salonika"},
    "thessaloniki": {"lat": 40.6401, "lon": 22.9444, "display_name": "Thessaloniki"},
    "corfu": {"lat": 39.6243, "lon": 19.9217, "display_name": "Corfu"},

    # === Eastern Europe (Jewish Publishing Centers) ===
    "vilna": {"lat": 54.6872, "lon": 25.2797, "display_name": "Vilna (Vilnius)"},
    "vilnius": {"lat": 54.6872, "lon": 25.2797, "display_name": "Vilnius"},
    "minsk": {"lat": 53.9006, "lon": 27.5590, "display_name": "Minsk"},
    "odessa": {"lat": 46.4825, "lon": 30.7233, "display_name": "Odessa"},
    "lviv": {"lat": 49.8397, "lon": 24.0297, "display_name": "Lviv"},
    "lemberg": {"lat": 49.8397, "lon": 24.0297, "display_name": "Lemberg (Lviv)"},
    "lwow": {"lat": 49.8397, "lon": 24.0297, "display_name": "Lwow (Lviv)"},
    "zhitomir": {"lat": 50.2547, "lon": 28.6587, "display_name": "Zhitomir"},
    "zhytomyr": {"lat": 50.2547, "lon": 28.6587, "display_name": "Zhytomyr"},
    "berdichev": {"lat": 49.8924, "lon": 28.5861, "display_name": "Berdichev"},
    "lublin": {"lat": 51.2465, "lon": 22.5684, "display_name": "Lublin"},
    "lodz": {"lat": 51.7592, "lon": 19.4560, "display_name": "Lodz"},
    "grodno": {"lat": 53.6779, "lon": 23.8298, "display_name": "Grodno"},
    "brest litovsk": {"lat": 52.0976, "lon": 23.7341, "display_name": "Brest-Litovsk"},
    "bialystok": {"lat": 53.1325, "lon": 23.1688, "display_name": "Bialystok"},
    "pinsk": {"lat": 52.1115, "lon": 26.1003, "display_name": "Pinsk"},
    "vitebsk": {"lat": 55.1904, "lon": 30.2049, "display_name": "Vitebsk"},
    "mohilev": {"lat": 53.8945, "lon": 30.3305, "display_name": "Mohilev"},
    "kiev": {"lat": 50.4501, "lon": 30.5234, "display_name": "Kiev"},
    "st. petersburg": {"lat": 59.9311, "lon": 30.3609, "display_name": "St. Petersburg"},
    "saint petersburg": {"lat": 59.9311, "lon": 30.3609, "display_name": "Saint Petersburg"},
    "moscow": {"lat": 55.7558, "lon": 37.6173, "display_name": "Moscow"},
    "riga": {"lat": 56.9496, "lon": 24.1052, "display_name": "Riga"},
    "tallinn": {"lat": 59.4370, "lon": 24.7536, "display_name": "Tallinn"},
    "dorpat": {"lat": 58.3780, "lon": 26.7290, "display_name": "Dorpat (Tartu)"},
    "czernowitz": {"lat": 48.2917, "lon": 25.9358, "display_name": "Czernowitz (Chernivtsi)"},
    "chernivtsi": {"lat": 48.2917, "lon": 25.9358, "display_name": "Chernivtsi"},
    "pressburg": {"lat": 48.1486, "lon": 17.1077, "display_name": "Pressburg (Bratislava)"},
    "bratislava": {"lat": 48.1486, "lon": 17.1077, "display_name": "Bratislava"},
    "bucharest": {"lat": 44.4268, "lon": 26.1025, "display_name": "Bucharest"},
    "belgrade": {"lat": 44.7866, "lon": 20.4489, "display_name": "Belgrade"},
    "sofia": {"lat": 42.6977, "lon": 23.3219, "display_name": "Sofia"},
    "zagreb": {"lat": 45.8150, "lon": 15.9819, "display_name": "Zagreb"},
    "trieste": {"lat": 45.6495, "lon": 13.7768, "display_name": "Trieste"},
    "gorizia": {"lat": 45.9403, "lon": 13.6219, "display_name": "Gorizia"},
    "koretz": {"lat": 50.6192, "lon": 27.7494, "display_name": "Koretz"},
    "slavuta": {"lat": 50.3000, "lon": 26.8667, "display_name": "Slavuta"},
    "zolkiew": {"lat": 49.9833, "lon": 23.9667, "display_name": "Zolkiew (Zhovkva)"},
    "shklov": {"lat": 54.2086, "lon": 30.2936, "display_name": "Shklov"},
    "kopys": {"lat": 54.3254, "lon": 30.5370, "display_name": "Kopys"},
    "dubno": {"lat": 50.4167, "lon": 25.7333, "display_name": "Dubno"},
    "ostrog": {"lat": 50.3267, "lon": 26.5161, "display_name": "Ostrog"},
    "brody": {"lat": 50.0814, "lon": 25.1533, "display_name": "Brody"},
    "tarnopol": {"lat": 49.5535, "lon": 25.5948, "display_name": "Tarnopol (Ternopil)"},
    "czortkow": {"lat": 49.0167, "lon": 25.8000, "display_name": "Czortkow (Chortkiv)"},
    "stanislawow": {"lat": 48.9226, "lon": 24.7111, "display_name": "Stanislawow (Ivano-Frankivsk)"},
    "przemysl": {"lat": 49.7842, "lon": 22.7678, "display_name": "Przemysl"},

    # === Americas ===
    "new york": {"lat": 40.7128, "lon": -74.0060, "display_name": "New York"},
    "philadelphia": {"lat": 39.9526, "lon": -75.1652, "display_name": "Philadelphia"},
    "boston": {"lat": 42.3601, "lon": -71.0589, "display_name": "Boston"},
    "baltimore": {"lat": 39.2904, "lon": -76.6122, "display_name": "Baltimore"},
    "cincinnati": {"lat": 39.1031, "lon": -84.5120, "display_name": "Cincinnati"},
    "chicago": {"lat": 41.8781, "lon": -87.6298, "display_name": "Chicago"},
    "san francisco": {"lat": 37.7749, "lon": -122.4194, "display_name": "San Francisco"},
    "washington": {"lat": 38.9072, "lon": -77.0369, "display_name": "Washington"},
    "buenos aires": {"lat": -34.6037, "lon": -58.3816, "display_name": "Buenos Aires"},
    "mexico city": {"lat": 19.4326, "lon": -99.1332, "display_name": "Mexico City"},
    "montreal": {"lat": 45.5017, "lon": -73.5673, "display_name": "Montreal"},
    "toronto": {"lat": 43.6532, "lon": -79.3832, "display_name": "Toronto"},
    "havana": {"lat": 23.1136, "lon": -82.3666, "display_name": "Havana"},
    "rio de janeiro": {"lat": -22.9068, "lon": -43.1729, "display_name": "Rio de Janeiro"},

    # === North Africa / Sephardic Centers ===
    "marrakech": {"lat": 31.6295, "lon": -7.9811, "display_name": "Marrakech"},
    "tangier": {"lat": 35.7595, "lon": -5.8340, "display_name": "Tangier"},
    "oran": {"lat": 35.6969, "lon": -0.6331, "display_name": "Oran"},
    "djerba": {"lat": 33.8075, "lon": 10.8451, "display_name": "Djerba"},

    # === India / Asia (Cochin Jewish community, Bombay publishing) ===
    "bombay": {"lat": 19.0760, "lon": 72.8777, "display_name": "Bombay (Mumbai)"},
    "mumbai": {"lat": 19.0760, "lon": 72.8777, "display_name": "Mumbai"},
    "calcutta": {"lat": 22.5726, "lon": 88.3639, "display_name": "Calcutta (Kolkata)"},
    "cochin": {"lat": 9.9312, "lon": 76.2673, "display_name": "Cochin"},
    "shanghai": {"lat": 31.2304, "lon": 121.4737, "display_name": "Shanghai"},

    # === Latin place-name forms (common in bibliographic records) ===
    "lugduni batavorum": {"lat": 52.1601, "lon": 4.4970, "display_name": "Leiden (Lugduni Batavorum)"},
    "lutetiae": {"lat": 48.8566, "lon": 2.3522, "display_name": "Paris (Lutetia)"},
    "lutetiae parisiorum": {"lat": 48.8566, "lon": 2.3522, "display_name": "Paris (Lutetia)"},
    "argentorati": {"lat": 48.5734, "lon": 7.7521, "display_name": "Strasbourg (Argentoratum)"},
    "basileae": {"lat": 47.5596, "lon": 7.5886, "display_name": "Basel (Basilea)"},
    "coloniae": {"lat": 50.9375, "lon": 6.9603, "display_name": "Cologne (Colonia)"},
    "coloniae agrippinae": {"lat": 50.9375, "lon": 6.9603, "display_name": "Cologne (Colonia Agrippina)"},
    "genevae": {"lat": 46.2044, "lon": 6.1432, "display_name": "Geneva (Genava)"},
    "venetiis": {"lat": 45.4408, "lon": 12.3155, "display_name": "Venice (Venetiis)"},
    "vindobonae": {"lat": 48.2082, "lon": 16.3738, "display_name": "Vienna (Vindobona)"},
    "berolini": {"lat": 52.5200, "lon": 13.4050, "display_name": "Berlin (Berolinum)"},
    "lipsiae": {"lat": 51.3397, "lon": 12.3731, "display_name": "Leipzig (Lipsia)"},
    "amstelodami": {"lat": 52.3676, "lon": 4.9041, "display_name": "Amsterdam (Amstelodamum)"},
    "hagae comitis": {"lat": 52.0705, "lon": 4.3007, "display_name": "The Hague (Haga Comitis)"},
    "londini": {"lat": 51.5074, "lon": -0.1278, "display_name": "London (Londinium)"},
    "trajecti ad rhenum": {"lat": 52.0907, "lon": 5.1214, "display_name": "Utrecht (Trajectum ad Rhenum)"},
    "ultrajecti": {"lat": 52.0907, "lon": 5.1214, "display_name": "Utrecht (Ultrajectum)"},
    "francofurti": {"lat": 50.1109, "lon": 8.6821, "display_name": "Frankfurt (Francofurtum)"},
    "francofurti ad moenum": {"lat": 50.1109, "lon": 8.6821, "display_name": "Frankfurt am Main (Francofurtum ad Moenum)"},
    "romae": {"lat": 41.9028, "lon": 12.4964, "display_name": "Rome (Roma)"},
    "neapoli": {"lat": 40.8518, "lon": 14.2681, "display_name": "Naples (Neapolis)"},
    "patavii": {"lat": 45.4064, "lon": 11.8768, "display_name": "Padua (Patavium)"},
    "bononiae": {"lat": 44.4949, "lon": 11.3426, "display_name": "Bologna (Bononia)"},
    "florentiae": {"lat": 43.7696, "lon": 11.2558, "display_name": "Florence (Florentia)"},
    "mediolani": {"lat": 45.4642, "lon": 9.1900, "display_name": "Milan (Mediolanum)"},
    "taurini": {"lat": 45.0703, "lon": 7.6869, "display_name": "Turin (Augusta Taurinorum)"},
    "genuae": {"lat": 44.4056, "lon": 8.9463, "display_name": "Genoa (Genua)"},
    "pistorii": {"lat": 43.9333, "lon": 10.9167, "display_name": "Pistoia (Pistorium)"},
    "antverpiae": {"lat": 51.2194, "lon": 4.4025, "display_name": "Antwerp (Antverpia)"},
    "bruxellis": {"lat": 50.8503, "lon": 4.3517, "display_name": "Brussels (Bruxella)"},
    "hafniae": {"lat": 55.6761, "lon": 12.5683, "display_name": "Copenhagen (Hafnia)"},
    "holmiae": {"lat": 59.3293, "lon": 18.0686, "display_name": "Stockholm (Holmia)"},
    "pragae": {"lat": 50.0755, "lon": 14.4378, "display_name": "Prague (Praga)"},
    "cracoviae": {"lat": 50.0647, "lon": 19.9450, "display_name": "Krakow (Cracovia)"},
    "varsaviae": {"lat": 52.2297, "lon": 21.0122, "display_name": "Warsaw (Varsovia)"},
    "oxonii": {"lat": 51.7520, "lon": -1.2577, "display_name": "Oxford (Oxonium)"},
    "cantabrigiae": {"lat": 52.2053, "lon": 0.1218, "display_name": "Cambridge (Cantabrigia)"},
    "edinburgi": {"lat": 55.9533, "lon": -3.1883, "display_name": "Edinburgh (Edinburgum)"},
    "norimbergae": {"lat": 49.4521, "lon": 11.0767, "display_name": "Nuremberg (Norimberga)"},
    "wratislaviae": {"lat": 51.1079, "lon": 17.0385, "display_name": "Breslau (Wratislavia)"},
    "petropoli": {"lat": 59.9311, "lon": 30.3609, "display_name": "St. Petersburg (Petropolis)"},
    "lugduni": {"lat": 45.7640, "lon": 4.8357, "display_name": "Lyon (Lugdunum)"},
    "moguntiae": {"lat": 49.9929, "lon": 8.2473, "display_name": "Mainz (Moguntia)"},
    "tubingae": {"lat": 48.5216, "lon": 9.0576, "display_name": "Tubingen (Tubinga)"},
    "gottingae": {"lat": 51.5328, "lon": 9.9354, "display_name": "Gottingen (Gottinga)"},
    "jenae": {"lat": 50.9271, "lon": 11.5892, "display_name": "Jena (Iena)"},
    "marburgi": {"lat": 50.8019, "lon": 8.7711, "display_name": "Marburg (Marburgum)"},
    "rostochii": {"lat": 54.0887, "lon": 12.1407, "display_name": "Rostock (Rostochium)"},

    # === Hebrew-script normalized place names ===
    # These are casefold-cleaned Hebrew place names that appear as place_norm
    # in the database when not resolved by the alias map
    "ירושלים": {"lat": 31.7683, "lon": 35.2137, "display_name": "Jerusalem"},
    "אמשטרדם": {"lat": 52.3676, "lon": 4.9041, "display_name": "Amsterdam"},
    "ונציה": {"lat": 45.4408, "lon": 12.3155, "display_name": "Venice"},
    "לונדון": {"lat": 51.5074, "lon": -0.1278, "display_name": "London"},
    "ברלין": {"lat": 52.5200, "lon": 13.4050, "display_name": "Berlin"},
    "וינה": {"lat": 48.2082, "lon": 16.3738, "display_name": "Vienna"},
    "פראג": {"lat": 50.0755, "lon": 14.4378, "display_name": "Prague"},
    "קושטנדינה": {"lat": 41.0082, "lon": 28.9784, "display_name": "Constantinople"},
    "שלוניקי": {"lat": 40.6401, "lon": 22.9444, "display_name": "Thessaloniki"},
    "ליוורנו": {"lat": 43.5485, "lon": 10.3106, "display_name": "Livorno"},
    "צפת": {"lat": 32.9646, "lon": 35.4960, "display_name": "Safed"},
    "חברון": {"lat": 31.5326, "lon": 35.0998, "display_name": "Hebron"},
    "טבריה": {"lat": 32.7940, "lon": 35.5300, "display_name": "Tiberias"},
    "תל אביב": {"lat": 32.0853, "lon": 34.7818, "display_name": "Tel Aviv"},
    "באזל": {"lat": 47.5596, "lon": 7.5886, "display_name": "Basel"},
    "פריז": {"lat": 48.8566, "lon": 2.3522, "display_name": "Paris"},
    "ליידן": {"lat": 52.1601, "lon": 4.4970, "display_name": "Leiden"},
    "רומא": {"lat": 41.9028, "lon": 12.4964, "display_name": "Rome"},
    "מנטובה": {"lat": 45.1564, "lon": 10.7914, "display_name": "Mantua"},
    "פיררה": {"lat": 44.8381, "lon": 11.6199, "display_name": "Ferrara"},
    "קראקוב": {"lat": 50.0647, "lon": 19.9450, "display_name": "Krakow"},
    "וילנה": {"lat": 54.6872, "lon": 25.2797, "display_name": "Vilna"},
    "ורשה": {"lat": 52.2297, "lon": 21.0122, "display_name": "Warsaw"},
    "לובלין": {"lat": 51.2465, "lon": 22.5684, "display_name": "Lublin"},
    "פיורדא": {"lat": 49.4709, "lon": 10.9888, "display_name": "Furth"},
    "בומבי": {"lat": 19.0760, "lon": 72.8777, "display_name": "Bombay"},
    "קהיר": {"lat": 30.0444, "lon": 31.2357, "display_name": "Cairo"},
    "בגדד": {"lat": 33.3152, "lon": 44.3661, "display_name": "Baghdad"},
    "חלב": {"lat": 36.2021, "lon": 37.1343, "display_name": "Aleppo"},
    "דמשק": {"lat": 33.5138, "lon": 36.2765, "display_name": "Damascus"},
    "ביירות": {"lat": 33.8938, "lon": 35.5018, "display_name": "Beirut"},
    "אלכסנדריה": {"lat": 31.2001, "lon": 29.9187, "display_name": "Alexandria"},
    "יפו": {"lat": 32.0534, "lon": 34.7509, "display_name": "Jaffa"},
    "עכו": {"lat": 32.9272, "lon": 35.0761, "display_name": "Acre"},
    "חיפה": {"lat": 32.7940, "lon": 34.9896, "display_name": "Haifa"},
    "ניו יורק": {"lat": 40.7128, "lon": -74.0060, "display_name": "New York"},

    # === Other Historical Publishing Centers ===
    "furth": {"lat": 49.4709, "lon": 10.9888, "display_name": "Furth"},
    "fuerth": {"lat": 49.4709, "lon": 10.9888, "display_name": "Furth"},
    "sulzbach": {"lat": 49.4967, "lon": 11.7469, "display_name": "Sulzbach"},
    "hanau": {"lat": 50.1340, "lon": 8.9154, "display_name": "Hanau"},
    "wandsbek": {"lat": 53.5833, "lon": 10.0833, "display_name": "Wandsbek"},
    "dyhernfurth": {"lat": 51.2500, "lon": 16.7667, "display_name": "Dyhernfurth (Brzeg Dolny)"},
    "thiengen": {"lat": 47.6500, "lon": 8.3000, "display_name": "Thiengen"},
    "wilhermsdorf": {"lat": 49.4833, "lon": 10.7167, "display_name": "Wilhermsdorf"},
    "amsterdam-leiden": {"lat": 52.2639, "lon": 4.6506, "display_name": "Amsterdam-Leiden"},
    "piotrkow": {"lat": 51.4047, "lon": 19.7031, "display_name": "Piotrkow Trybunalski"},
    "zhovkva": {"lat": 49.9833, "lon": 23.9667, "display_name": "Zhovkva"},

    # === Iberian Peninsula (pre-expulsion Jewish centers) ===
    "granada": {"lat": 37.1773, "lon": -3.5986, "display_name": "Granada"},
    "cordoba": {"lat": 37.8882, "lon": -4.7794, "display_name": "Cordoba"},
    "zaragoza": {"lat": 41.6488, "lon": -0.8891, "display_name": "Zaragoza"},
    "girona": {"lat": 41.9794, "lon": 2.8214, "display_name": "Girona"},
    "valencia": {"lat": 39.4699, "lon": -0.3763, "display_name": "Valencia"},

    # === Miscellaneous well-known cities ===
    "helsinki": {"lat": 60.1699, "lon": 24.9384, "display_name": "Helsinki"},
    "athens": {"lat": 37.9838, "lon": 23.7275, "display_name": "Athens"},
    "tehran": {"lat": 35.6892, "lon": 51.3890, "display_name": "Tehran"},
    "cape town": {"lat": -33.9249, "lon": 18.4241, "display_name": "Cape Town"},
    "johannesburg": {"lat": -26.2041, "lon": 28.0473, "display_name": "Johannesburg"},
    "melbourne": {"lat": -37.8136, "lon": 144.9631, "display_name": "Melbourne"},
    "sydney": {"lat": -33.8688, "lon": 151.2093, "display_name": "Sydney"},
    "hong kong": {"lat": 22.3193, "lon": 114.1694, "display_name": "Hong Kong"},
    "singapore": {"lat": 1.3521, "lon": 103.8198, "display_name": "Singapore"},
    "tokyo": {"lat": 35.6762, "lon": 139.6503, "display_name": "Tokyo"},
    "delhi": {"lat": 28.7041, "lon": 77.1025, "display_name": "Delhi"},
    "st. louis": {"lat": 38.6270, "lon": -90.1994, "display_name": "St. Louis"},
    "detroit": {"lat": 42.3314, "lon": -83.0458, "display_name": "Detroit"},
    "cleveland": {"lat": 41.4993, "lon": -81.6944, "display_name": "Cleveland"},
    "pittsburgh": {"lat": 40.4406, "lon": -79.9959, "display_name": "Pittsburgh"},
    "los angeles": {"lat": 34.0522, "lon": -118.2437, "display_name": "Los Angeles"},
    "seattle": {"lat": 47.6062, "lon": -122.3321, "display_name": "Seattle"},
    "minneapolis": {"lat": 44.9778, "lon": -93.2650, "display_name": "Minneapolis"},
    "new haven": {"lat": 41.3083, "lon": -72.9279, "display_name": "New Haven"},
    "newark": {"lat": 40.7357, "lon": -74.1724, "display_name": "Newark"},
    "brooklyn": {"lat": 40.6782, "lon": -73.9442, "display_name": "Brooklyn"},
    "hartford": {"lat": 41.7658, "lon": -72.6734, "display_name": "Hartford"},
    "albany": {"lat": 42.6526, "lon": -73.7562, "display_name": "Albany"},
    "providence": {"lat": 41.8240, "lon": -71.4128, "display_name": "Providence"},
    "new orleans": {"lat": 29.9511, "lon": -90.0715, "display_name": "New Orleans"},
    "richmond": {"lat": 37.5407, "lon": -77.4360, "display_name": "Richmond"},
    "savannah": {"lat": 32.0809, "lon": -81.0912, "display_name": "Savannah"},
    "charleston": {"lat": 32.7765, "lon": -79.9311, "display_name": "Charleston"},

    # === Additional European cities ===
    "pozsony": {"lat": 48.1486, "lon": 17.1077, "display_name": "Pozsony (Bratislava)"},
    "brno": {"lat": 49.1951, "lon": 16.6068, "display_name": "Brno"},
    "olomouc": {"lat": 49.5938, "lon": 17.2509, "display_name": "Olomouc"},
    "innsbruck": {"lat": 47.2692, "lon": 11.4041, "display_name": "Innsbruck"},
    "graz": {"lat": 47.0707, "lon": 15.4395, "display_name": "Graz"},
    "salzburg": {"lat": 47.8095, "lon": 13.0550, "display_name": "Salzburg"},
    "linz": {"lat": 48.3069, "lon": 14.2858, "display_name": "Linz"},
    "poznan": {"lat": 52.4064, "lon": 16.9252, "display_name": "Poznan"},
    "posen": {"lat": 52.4064, "lon": 16.9252, "display_name": "Posen (Poznan)"},
    "thorn": {"lat": 53.0138, "lon": 18.5984, "display_name": "Thorn (Torun)"},
    "torun": {"lat": 53.0138, "lon": 18.5984, "display_name": "Torun"},
    "stettin": {"lat": 53.4285, "lon": 14.5528, "display_name": "Stettin (Szczecin)"},
    "szczecin": {"lat": 53.4285, "lon": 14.5528, "display_name": "Szczecin"},
    "worms": {"lat": 49.6341, "lon": 8.3507, "display_name": "Worms"},
    "speyer": {"lat": 49.3173, "lon": 8.4411, "display_name": "Speyer"},
    "regensburg": {"lat": 49.0134, "lon": 12.1016, "display_name": "Regensburg"},
    "passau": {"lat": 48.5748, "lon": 13.4609, "display_name": "Passau"},
    "trier": {"lat": 49.7490, "lon": 6.6371, "display_name": "Trier"},
    "aachen": {"lat": 50.7753, "lon": 6.0839, "display_name": "Aachen"},
    "munster": {"lat": 51.9607, "lon": 7.6261, "display_name": "Munster"},
    "dortmund": {"lat": 51.5136, "lon": 7.4653, "display_name": "Dortmund"},
    "bremen": {"lat": 53.0793, "lon": 8.8017, "display_name": "Bremen"},
    "braunschweig": {"lat": 52.2689, "lon": 10.5268, "display_name": "Braunschweig"},
    "celle": {"lat": 52.6261, "lon": 10.0808, "display_name": "Celle"},
    "emden": {"lat": 53.3670, "lon": 7.2059, "display_name": "Emden"},
    "aurich": {"lat": 53.4708, "lon": 7.4831, "display_name": "Aurich"},
    "oldenburg": {"lat": 53.1435, "lon": 8.2146, "display_name": "Oldenburg"},
    "schwerin": {"lat": 53.6355, "lon": 11.4012, "display_name": "Schwerin"},
    "wismar": {"lat": 53.8920, "lon": 11.4650, "display_name": "Wismar"},
    "stralsund": {"lat": 54.3096, "lon": 13.0818, "display_name": "Stralsund"},
    "neuchatel": {"lat": 46.9900, "lon": 6.9293, "display_name": "Neuchatel"},
    "schaffhausen": {"lat": 47.6960, "lon": 8.6340, "display_name": "Schaffhausen"},
    "st. gallen": {"lat": 47.4245, "lon": 9.3767, "display_name": "St. Gallen"},
    "lucerne": {"lat": 47.0502, "lon": 8.3093, "display_name": "Lucerne"},
    "verona": {"lat": 45.4384, "lon": 10.9916, "display_name": "Verona"},
    "vicenza": {"lat": 45.5455, "lon": 11.5354, "display_name": "Vicenza"},
    "treviso": {"lat": 45.6669, "lon": 12.2430, "display_name": "Treviso"},
    "bergamo": {"lat": 45.6983, "lon": 9.6773, "display_name": "Bergamo"},
    "como": {"lat": 45.8081, "lon": 9.0852, "display_name": "Como"},
    "pavia": {"lat": 45.1847, "lon": 9.1582, "display_name": "Pavia"},
    "catania": {"lat": 37.5079, "lon": 15.0830, "display_name": "Catania"},
    "messina": {"lat": 38.1938, "lon": 15.5540, "display_name": "Messina"},
    "bari": {"lat": 41.1171, "lon": 16.8719, "display_name": "Bari"},
    "lecce": {"lat": 40.3516, "lon": 18.1720, "display_name": "Lecce"},
    "cagliari": {"lat": 39.2238, "lon": 9.1217, "display_name": "Cagliari"},
}

# Place_norm values to skip (not geocodable)
NON_GEOCODABLE = {
    "[sine loco]",
    "sine loco",
    "s.l.",
    "[s.l.]",
    "place of publication not identified",
    "unknown",
    "[unknown]",
    "not identified",
    "place not identified",
    "[place of publication not identified]",
    "",
}


def generate_geocodes(db_path: Path | None = None) -> dict:
    """Generate place geocodes dictionary.

    If db_path is provided and exists, queries the database for distinct
    place_norm values and returns geocodes for matched places.
    Otherwise, returns the full built-in mapping.

    Args:
        db_path: Optional path to bibliographic.db

    Returns:
        Dictionary mapping place_norm to {lat, lon, display_name}
    """
    if db_path and db_path.exists():
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT DISTINCT place_norm FROM imprints "
            "WHERE place_norm IS NOT NULL ORDER BY place_norm"
        ).fetchall()
        conn.close()

        db_places = {row[0] for row in rows}
        geocodes = {}
        unmatched = []

        for place in sorted(db_places):
            if place.lower().strip() in NON_GEOCODABLE:
                continue
            if place in PLACE_GEOCODES:
                geocodes[place] = PLACE_GEOCODES[place]
            else:
                unmatched.append(place)

        if unmatched:
            print(f"WARNING: {len(unmatched)} place_norm values not geocoded:")
            for p in unmatched[:20]:
                print(f"  - {p!r}")
            if len(unmatched) > 20:
                print(f"  ... and {len(unmatched) - 20} more")

        return geocodes
    else:
        # Return the full built-in mapping
        return dict(PLACE_GEOCODES)


def main():
    """Generate place_geocodes.json."""
    project_root = Path(__file__).resolve().parent.parent.parent
    db_path = project_root / "data" / "index" / "bibliographic.db"
    output_path = project_root / "data" / "normalization" / "place_geocodes.json"

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    geocodes = generate_geocodes(db_path if db_path.exists() else None)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(geocodes, f, indent=2, ensure_ascii=False)

    print(f"Wrote {len(geocodes)} place geocodes to {output_path}")
    return geocodes


if __name__ == "__main__":
    main()
