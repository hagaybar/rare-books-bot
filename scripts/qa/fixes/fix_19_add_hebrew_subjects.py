"""Fix 19: Add Hebrew translations to subject headings.

Adds a `value_he` column to the subjects table and populates it with Hebrew
translations using a component-based approach: base terms + subdivisions are
translated independently, then composed. Also rebuilds the subjects_fts index
to include Hebrew values for bilingual search.

One-time enrichment — translations by Claude (Opus 4).
"""

import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[3] / "data" / "index" / "bibliographic.db"

# =============================================================================
# BASE TERM TRANSLATIONS  (English base → Hebrew, with synonyms)
# =============================================================================
BASE_TRANSLATIONS: dict[str, str] = {
    # ── Judaica / Religious ────────────────────────────────────────��─────
    "Aaron": "אהרן",
    "Abraham": "אברהם",
    "Aggada": "אגדה",
    "Bible": "תנ\"ך מקרא כתבי הקודש",
    "Blood accusation": "עלילת דם",
    "Cabala": "קבלה",
    "Commandments, Six hundred and thirteen": "תרי\"ג מצוות שש מאות ושלוש עש��ה מצוות",
    "Conversion": "גיור המרת דת",
    "Death": "מוות",
    "Easter": "פסחא",
    "God": "אלוהים",
    "God (Judaism)": "אלוהים ביהדות",
    "Haftarot": "הפטרות",
    "Haggadah": "הגדה הגדה של פסח",
    "Hasidism": "חסידות",
    "Hiddushim (Jewish law)": "חידושים",
    "Holocaust, Jewish (1939-1945)": "שואה השואה",
    "Hoshana Rabba": "הושענא רבה",
    "Idols and images": "עבודה זרה פסלים",
    "Isaac": "יצחק",
    "Islam": "אסלאם",
    "Israel": "ישראל",
    "Jacob": "יעקב",
    "Jesus": "ישו",
    "Jewish artists": "אמנים יהודים",
    "Jewish authors": "סופרים יהודים מחברים יהודים",
    "Jewish ethics": "מוסר אתיקה יהודית",
    "Jewish families": "משפחות יהודיות",
    "Jewish illumination of books and manuscripts": "הארת ספרים ��כתבי יד יהודים",
    "Jewish law": "הלכה משפט עברי",
    "Jewish legends": "אגדות יהודיות",
    "Jewish liturgy": "ליטורגיה יהודית תפילה פולחן",
    "Jewish magic": "כישוף יהודי מאגיה",
    "Jewish painters": "ציירים יהודים",
    "Jewish philosophers": "פילוסופים יהודים",
    "Jewish philosophy": "פילוסופיה יהודית מחשבת ישראל",
    "Jewish sermons": "דרשות",
    "Jewish women": "נשים יהודיות",
    "Jews": "יהודים",
    "Jews, Ethiopian": "יהודי אתיופיה ביתא ישראל פלאשים",
    "Jews, Moroccan": "יהודי מרוקו",
    "Judaism": "יהדות",
    "Karaites": "קראים",
    "Karaitic literature": "ספרות קראית",
    "Kinot": "קינות",
    "Mahzor": "מחזור",
    "Messiah": "משיח",
    "Midrash": "מדרש",
    "Midrash ha-gadol": "מדרש הגדול",
    "Midrash rabbah": "מדרש רבה",
    "Mishnah": "משנה",
    "Moses": "משה",
    "Music in the Bible": "מוזיקה במקרא",
    "Mysticism": "מיסטיקה",
    "Passover": "פסח",
    "Piyyutim": "פיוטים פיוט",
    "Prayer": "תפילה",
    "Preaching": "דרשנות",
    "Purim": "פורים",
    "Rabbinical literature": "ספרות רבנית",
    "Rabbis": "רבנים",
    "Religion": "דת",
    "Repentance": "תשובה חזרה בתשובה",
    "Responsa": "שו\"ת שאלות ותשובות תשובות",
    "Sabbath": "��בת",
    "Sabbathaians": "שבתאים",
    "Sarah": "שרה",
    "Selihot": "סליחות",
    "Siddur": "סידור",
    "Sukkot": "סוכות",
    "Synagogue music": "מוזיקת בית כנסת חזנות",
    "Synagogues": "בתי כנסת",
    "Talmud Bavli": "תלמוד בבלי",
    "Ten commandments": "עשרת הדיברות",
    "Theology": "תיאולוגיה",
    "Theology, Doctrinal": "תיאולוגיה דוגמטית",
    "Western Wall (Jerusalem)": "הכותל המערבי",
    "Yom Kippur": "יום כיפור יום הכיפורים",
    "Zionism": "ציונות",
    "Zohar": "זוהר",
    # ── Book / Printing / Library ────────────────────────────────────────
    "Antiquarian booksellers": "מוכרי ספר��ם עתיקים",
    "Bibliography": "ביבליוגרפיה",
    "Bibliomania": "ביבל��ומניה אהבת ספרים",
    "Block books": "ספרי חיתוך עץ",
    "Block books, German": "ספרי חיתוך עץ גרמניים",
    "Book auctions": "מכירות פומביות ספרים",
    "Book catalogs": "קטלוגי ספרים",
    "Book collecting": "אס��נות ספרים",
    "Book collectors": "אספני ספרים",
    "Book design": "עיצוב ספרים",
    "Book industries and trade": "תעשיית הספר מסחר בספרים",
    "Bookbinders": "כורכי ספרים",
    "Bookbinding": "כריכה כריכת ספרים",
    "Bookplate designers": "מעצבי תוויות ספרים",
    "Bookplates": "תוויות ספרים אקס ליבריס",
    "Bookplates, Belgian": "תוויות ספרים בלגיות",
    "Bookplates, Dutch": "תוויות ספרים הולנדיו��",
    "Bookplates, English": "תוויות ספרים אנגליות",
    "Bookplates, French": "תוויות ספרים צרפתיות",
    "Bookplates, German": "תוויות ספרים גרמניות",
    "Bookplates, Italian": "תוויות ספרים איטלקיות",
    "Bookplates, Spanish": "תוויות ספרים ספרדיות",
    "Books": "ספרים",
    "Books and reading": "ספרים וקריאה",
    "Booksellers and bookselling": "מוכרי ספרים מסחר בספרים",
    "Booksellers' catalogs": "קטלוגי מוכרי ספרים",
    "Classification": "סיווג",
    "Early printed books": "דפוסים ראשו��ים ספרים מודפסים מוקדמים",
    "Freedom of the press": "חופש העיתונות",
    "Hebrew imprints": "דפוסים עבריים",
    "Illumination of books and manuscripts": "הארת ספרים וכתבי יד",
    "Illustrated books": "ספרים מאוירים",
    "Illustration of books": "איור ספרים",
    "Illustrators": "מאיירים",
    "Incunabula": "אינקונבולה דפוסי ערש",
    "Lettering": "כתיבת אותיות",
    "Librarians": "ספרנים",
    "Libraries": "ספריות",
    "Limited editions": "מהדורות מצומצמות",
    "Miniature books": "ספרים מיניאטוריים",
    "Papermaking": "ייצור נייר",
    "Press": "עיתונות",
    "Printers": "מדפיסים דפוסים",
    "Printers' marks": "סימני מדפיסים",
    "Printing": "דפוס הדפסה",
    "Printing, Hebrew": "דפוס עברי",
    "Prints in paste": "הדפסים בדבק",
    "Private libraries": "ספריות פרטיות",
    "Private press books": "ספרי דפוס פ��טי",
    "Private presses": "דפוסים פרטיים",
    "Prohibited books": "ספרים אסורים",
    "Publishers and publishing": "הוצאה לאור",
    "Rare books": "ספרים נדירים",
    "Type and type-founding": "טיפוגרפיה יציקת אותיות",
    "Writing": "כתיבה",
    # ── Languages ────────────────────────────────────────────────────────
    "Alphabet": "אלפבית אלף-בית",
    "Arabic drama": "דרמה ערבית",
    "Arabic language": "ערבית השפה הערבית",
    "Arabic literature": "ספרות ערבית",
    "Aramaic language": "ארמית",
    "Danish literature": "ספרות דנית",
    "English drama": "דרמה אנגלית",
    "English drama (Comedy)": "קומדיה אנגלית",
    "English fiction": "סיפורת אנגלית",
    "English literature": "ספרות אנגלית",
    "English newspapers": "עיתונים אנגליים",
    "English poetry": "שירה אנגלית",
    "English wit and humor": "הומור אנגלי",
    "Ethiopic language": "אתיופית געז",
    "Ethiopic literature": "ספרות אתיופית",
    "French drama": "דרמה צרפתית",
    "French essays": "מסות צרפתיות",
    "French fiction": "סיפורת צרפתית",
    "French language": "צרפתית",
    "French literature": "ספרות צרפתית",
    "French poetry": "שירה צרפתית",
    "German drama": "דרמה גרמנית",
    "German fiction": "סיפורת גרמנית",
    "German language": "גרמנית",
    "German literature": "ספרות גרמנית",
    "German poetry": "שירה גרמנית",
    "German wit and humor": "הומור גרמני",
    "Greek language": "יוונית",
    "Greek language, Biblical": "יוונית מקראית",
    "Greek literature": "ספרות יוונית",
    "Hebrew drama": "דרמה עברית",
    "Hebrew fiction": "סיפורת עברית בדיון עברי",
    "Hebrew language": "עברית השפה העברית",
    "Hebrew language, Biblical": "עברית מקראית",
    "Hebrew language, Post-Biblical": "עברית שלאחר המקרא",
    "Hebrew letters": "מכתבים עבריים אגרות",
    "Hebrew literature": "ספרות עברית",
    "Hebrew literature, Medieval": "ספרות עברית ימי הביניים",
    "Hebrew literature, Modern": "ספרות עברית מודרנית",
    "Hebrew poetry": "שירה עברית",
    "Hebrew poetry, Biblical": "שירת המקרא",
    "Hebrew poetry, Medieval": "שירה עברית ימי הביניים",
    "Italian language": "איטלקית",
    "Italian literature": "ספרות איטלקית",
    "Italian poetry": "שירה איטלקית",
    "Latin language": "לטינית",
    "Latin language, Medieval and modern": "לטינית ימי הביניים",
    "Latin literature": "ספרות לטינית",
    "Latin literature, Medieval and modern": "ספרות לטינית ימי הביניים",
    "Latin poetry": "שירה לטינית",
    "Latin poetry, Medieval and modern": "שירה לטינית ימי הביניים",
    "Neo-Latin poetry": "שירה ניאו-לטינית",
    "Persian language": "פרסית",
    "Russian fiction": "סיפורת רוסית",
    "Russian language": "רוסית",
    "Samaritan Aramaic language": "ארמית שומרונית",
    "Semitic languages": "שפות שמיות",
    "Semitic languages, Northwest": "שפות שמיות צפון-מערביות",
    "Short stories, Italian": "סיפורים קצרים איטלקיים",
    "Spanish language": "ספרדית",
    "Spanish literature": "ספרות ספרדית",
    "Syriac language": "סורית",
    "Yiddish drama": "דרמה ביידיש",
    "Yiddish language": "אידיש יידיש",
    "Yiddish literature": "ספרות אידיש",
    "Yiddish poetry": "שירה ביידיש",
    # ── Sciences / Arts / Philosophy ─────────────────────────────────────
    "Actresses": "שחקניות",
    "Agriculture": "חקלאות",
    "Alchemy": "אלכימיה",
    "Animals": "בעלי חיים חיות",
    "Architecture": "אדריכלות",
    "Arithmetic": "חשבון אריתמטיקה",
    "Art": "אמנות",
    "Botany": "בוטניקה",
    "Caricatures and cartoons": "קריקטורות",
    "Christian art and symbolism": "אמנות נוצרית וסמלים",
    "Christian ethics": "אתיקה נוצרית",
    "Christian literature": "ספרות נוצרית",
    "Christian saints": "קדושים נוצרים",
    "Christianity and other religions": "נצרות ודתות אחרות",
    "Church history": "תולדות הכנסייה",
    "Civil law": "משפט אזרחי",
    "Classical antiquities": "עתיקות קלאסיות",
    "Classical biography": "ביוגרפיה קלאסית",
    "Classical literature": "ספרות קלאסית",
    "Commerce": "מסחר",
    "Courtesy": "נימוסים",
    "Drawing": "ציור רישום",
    "Economics": "כלכלה",
    "Education": "חינוך",
    "Engravers": "חרטים",
    "Engraving": "חריטה",
    "Engraving, Dutch": "חריטה הולנדית",
    "Entomology": "חרקים אנטומולוגיה",
    "Erotic literature": "ספרות ארוטית",
    "Ethics": "אתיקה מוסר",
    "Fables, Arabic": "משלים ערביים",
    "Fables, French": "משלים צרפתיים",
    "Fairy tales": "��גדות סיפורי פיות",
    "Finance, Public": "מימון ציבורי",
    "Fire": "אש",
    "Folly": "שטות",
    "Fortification": "ביצור",
    "Geography": "גיאוגרפיה",
    "Heat": "חום",
    "History": "היסטוריה תולדות",
    "History, Ancient": "היסטוריה עתיקה",
    "Insects": "חרקים",
    "Invertebrates": "חס��י חוליות",
    "Law": "משפט",
    "Law, Germanic": "משפט גרמני",
    "Literary forgeries and mystifications": "זיופים ספרותיים",
    "Literature": "ספרות",
    "Locusts": "ארבה",
    "Manuscripts": "כתבי יד",
    "Manuscripts, Ethiopic": "כתבי יד אתיופיים",
    "Manuscripts, Hebrew": "כתבי יד עבריים",
    "Manuscripts, Latin": "כתבי יד לטיניים",
    "Mathematics": "מתמטיקה",
    "Mathematics, Greek": "מתמטיקה יוונית",
    "Medicine": "רפואה",
    "Medicine, Medieval": "רפואה ימי הביניים",
    "Military art and science": "אמנות צבאית מדע צבאי",
    "Military history": "היסטוריה צבאית",
    "Music": "מוזיקה",
    "Mythology, Classical": "מיתולוגיה קלאסית",
    "Mythology, Greek": "מיתולוגיה יוונית",
    "Natural history": "היסטוריה טבעית תולדות הטבע",
    "Natural theology": "תיאולוגיה טבעית",
    "Naturalization": "התאזרחות",
    "Parasites": "טפילים",
    "Philosophy": "פילוסופיה",
    "Philosophy, Ancient": "פילוסופיה עתיקה",
    "Philosophy, French": "פילוסופיה צרפתית",
    "Philosophy, German": "פילוסופיה גרמנית",
    "Picaresque literature": "ספרות פיקרסקית",
    "Plants": "צמחים",
    "Political ethics": "אתיקה פוליטית",
    "Political science": "מדע המדינה",
    "Psychology": "פסיכולוגיה",
    "Rhetoric": "רטוריקה",
    "Rhetoric, Ancient": "רטוריקה עתיקה",
    "Roman law": "משפט רומי",
    "Science": "מדע",
    "Silkworms": "תולעי משי",
    "Soul": "נשמה נפש",
    "Spontaneous generation": "יצירה ספונטנית",
    "Theater": "תיאטרון",
    "Voyages and travels": "מסעות",
    "War": "מלחמה",
    "Zoology": "זואולוגיה",
    "Zoologists": "זואולוגים",
    # ── People types ─────────────────────────────────────────────────────
    "Architects": "אדריכלים",
    "Artists": "אמנים",
    "Authors": "סופרים מחברים",
    "Authors, French": "סופרים צרפתיים",
    "Authors, German": "סופרים גרמניים",
    "Authors, Italian": "סופרים איטלקיים",
    "Authors, Medieval": "סופרים ימי הביניים",
    "Biography": "ביוגרפיה",
    "Composers": "מלחינים",
    "Emperors": "קיסרים",
    "Kings and rulers": "מלכים ושליטים",
    "Lithographers": "ליתוגרפים",
    "Nobility": "אצולה",
    "Painters": "ציירים",
    "Philosophers": "פילוסופים",
    "Physicians": "רופאים",
    "Poets, American": "משוררים אמריקאים",
    "Poets, English": "משוררים אנגליים",
    "Statesmen": "מדינאים",
    "Women": "נשים",
    "Women authors, Greek": "סופרות יווניות",
    "Wood-engravers": "חרטי עץ",
    "Wood-engraving": "חריטת עץ",
    "Wood-engraving, French": "חריטת עץ צרפתית",
    "Wood-engraving, German": "חריטת עץ גרמנית",
    "Wood-engraving, Italian": "חריטת עץ איטלקית",
    "Working class": "מעמד פועלים",
    # ── Geography ────────────────────────────────────────────────────────
    "Arabian Peninsula": "חצי האי ערב",
    "Asia": "אסיה",
    "Austria": "אוסטריה",
    "Belgium": "בלגיה",
    "Brittany (France)": "ברטאן צרפת",
    "Dauphiné (France)": "דופינה צרפת",
    "Egypt": "מצרים",
    "Eretz Israel": "ארץ ישראל",
    "Ethiopia": "אתיופיה",
    "Europe": "אירופה",
    "Europe, Western": "מערב אירופה",
    "Florence (Italy)": "פירנצה",
    "France": "צרפת",
    "Germany": "גרמניה",
    "Great Britain": "בריטניה אנגליה",
    "Greece": "יוון",
    "Holy Roman Empire": "האימפריה הרומית הקדושה",
    "India": "הודו",
    "Islamic Empire": "האימפריה האסלאמית",
    "Istanbul (Turkey)": "איסטנבול קושטא",
    "Italy": "איטליה",
    "Japan": "יפן",
    "Jerusalem (Israel)": "ירושלים",
    "Jordan": "ירדן",
    "Lorraine (France)": "לורן צרפת",
    "Middle East": "��מז��ח התיכון",
    "Netherlands": "הולנד הנידרלנדים",
    "Paris (France)": "פריז",
    "Poland": "פולין",
    "Portugal": "פורטוגל",
    "Rome": "רומא",
    "Russia": "רוסיה",
    "Saint Helena": "ס��ט הלנה",
    "Saint Petersburg (Russia)": "סנט פטרבורג",
    "Spain": "ספרד",
    "Syria": "סוריה",
    "Turkey": "טורקיה",
    "United States": "ארצות הברית",
    "Venice (Italy)": "ונציה",
    # ── Historical events ────────────────────────────────────────────────
    "Antisemitism": "אנטישמיות",
    "Apologetics": "אפולוגטיקה",
    "Autographs": "חתימות אוטוג��פים",
    "Battles": "קרבות",
    "Censorship": "צנזורה",
    "Cities and towns": "ערים ועיירות",
    "Crusades": "מסעי הצלב",
    "Inquisition": "אינקוויזיציה",
    "Jesuits": "ישועים",
    "Knights of Malta": "אבירי מלטה",
    "Napoleonic Wars, 1800-1815": "מלחמות נפוליאון",
    "National socialism": "נאציזם",
    "Peninsular War, 1807-1814": "מלחמת חצי האי האיברי",
    "Protestants": "פרו��סטנטים",
    "Reformation": "רפורמציה",
    "Seven Years' War, 1756-1763": "מלחמת שבע השנים",
    "Spanish Succession, War of, 1701-1714": "מלחמת הירושה הספרדית",
    "World War, 1914-1918": "מלחמת העולם ��ראשונה",
    "World War, 1939-1945": "מלחמת העולם השנייה",
    # ── Literary forms / misc ────────────────────────────────────────────
    "Aphorisms and apothegms": "פתגמים אמרות",
    "Canon law": "משפט קנוני",
    "Catholic Church": "הכנסייה הקתולית",
    "Ecclesiastical geography": "גיאוגרפיה כנסייתית",
    "Ecclesiastical law": "דין כנסייתי",
    "Land settlement": "התיישבות",
    "Marriage law": "דיני נישואין",
    "Motets": "מוטטות",
    "Names in the Bible": "שמות במקרא",
    "Names, Geographical": "שמות מקומות",
    "Ordinances, Municipal": "תקנות עירוניות",
    "Romances": "רומנסות",
    "Satire, English": "סטירה אנגלית",
    "Siege artillery": "ארטילריית מצור",
    "Siege warfare": "לחימת מצור",
    "Sieges": "מצורים",
    "Taxation": "מיסוי",
    "Wit and humor": "הומור",
    # ── Known persons (Hebrew forms) ─────────────────────────────────────
    "Caro, Yosef ben Efrayim,": "קארו יוסף בן אפרים מרן",
    "Maimonides, Moses,": "רמב\"ם משה בן מימון",
    "Rashi,": "רש\"י שלמה יצחקי",
    "Kimhi, David,": "רד\"ק דוד קמחי",
    "Luzzatto, Moshe Hayyim,": "רמח\"ל משה חיים לוצאטו",
    "Mendelssohn, Moses,": "משה מנדלסון",
    "Herzl, Theodor,": "תיאודור הרצל",
    "Josephus, Flavius": "יוסף בן מתתיהו יוסיפוס",
    "Weil, Jacob ben Judah,": "יעקב בן יהודה וייל",
    "Aristotle": "אריסטו",
    "Hippocrates": "היפוקרטס",
    "Homer": "הומרוס",
    "Horace": "הורציוס",
    "Ovid,": "��ובידיוס",
    "Pliny,": "פליניוס",
    "Plutarch": "פלוטרכוס",
    "Socrates": "סוקרטס",
    "Cicero, Marcus Tullius": "קיקרו",
    "Napoléon": "נפוליאון",
    "Boethius,": "בואתיוס",
    "Erasmus, Desiderius,": "אראסמוס",
    "Epictetus": "אפיקטטוס",
    "Theophrastus": "תיאופרסטוס",
    "Seneca, Lucius Annaeus,": "סנקה",
    "Voltaire,": "וולטר",
    "Chagall, Marc,": "מארק שאגאל",
    "Muhammad,": "מוחמד",
    "Alfasi, Isaac ben Jacob,": "הרי\"ף יצחק אלפסי",
    "Amichai, Yehuda, 1924-2000": "יהודה עמיחי",
    "Spinoza, Benedictus de,": "שפינוזה ברוך",
    "Descartes, René,": "דקארט",
    "Struck, Hermann,": "הרמן שטרוק",
    "Rubin, Reuven,": "ראובן רובין",
    "Birnbaum, Uriel,": "אוריאל בירנבאום",
    # Ethiopian church
    "YaʼItyop̣yā ʼortodoks tawāḥedo béta kerestiyān": "הכנסייה האורתודוקסית האתיופית",
    "YaʼItyop̣yā ʼortodoks tawāḥedo béta kerestiyān.": "הכנסייה האורתודוקסית האתיופית",
    # ── Belgian / misc literature ────────────────────────────────────────
    "Belgian literature (French)": "ספרות בלגית צרפתית",
    "Biblical costume": "לבוש מקראי",
    "Picaresque literature": "ספרות פיקרסקית",
    "Sermons, German": "דרשות גרמניות",
    # ── Additional important concepts ────────────────────────────────────
    "Apologetics": "אפולוגטיקה",
    "Antichrist": "אנטיכריסט",
    "Apprentices": "שוליות חניכים",
    "Ambassadors": "שגרירים",
    "Anarchism": "אנרכיזם",
    "Anthropology": "אנתרופולוגיה",
    "Algebra": "אלגברה",
    "Aesthetics": "אסתטיקה",
    "Auctions": "מכירות פומביות",
    "Canon law": "משפט קנוני",
    "Masorah": "מסורה",
    "New Testament": "הברית החדשה",
    "Apocrypha": "ספרים חיצוניים אפוקריפה",
    "Biblical costume": "לבוש מקראי",
    "Printing -- History": "תולד��ת הדפוס",
    "Paper industry": "תעשיית הנייר",
    "Qurʼan": "קוראן",
}

# =============================================================================
# SUBDIVISION TRANSLATIONS
# =============================================================================
SUBDIVISION_TRANSLATIONS: dict[str, str] = {
    # ── General subdivisions ─────────────────────────────────────────────
    "Accents and accentuation": "ני��וד וטעמים",
    "Adaptations": "עיבודים",
    "Alphabet": "אלפבית",
    "Anniversaries, etc": "יובלות",
    "Antiquities": "עתיקות",
    "Apologetic works": "כתבים אפולוגטיים",
    "Appreciation": "הערכה",
    "Armed Forces": "צבא כוחות מזוינים",
    "Art": "אמנות",
    "Art collections": "אוספי אמנות",
    "Behavior": "התנהגות",
    "Biblical teaching": "מוסר מקראי",
    "Bibliography": "ביבליוגרפיה",
    "Bio-bibliography": "ביו-ביבליוגרפיה",
    "Biography": "ביוגרפיה",
    "Books and reading": "ספרים וקריאה",
    "Buildings, structures, etc": "מבנים",
    "Campaigns": "מסעות מלחמה",
    "Caricatures and cartoons": "קריקטורות",
    "Catalogs": "קטלוגים",
    "Causes": "סיבות",
    "Charters, grants, privileges": "פריבילגיות זכויות",
    "Christian interpretations": "פרשנות נוצרית",
    "Christianity": "נצרות",
    "Chronicles": "כרוניקות דברי הימים",
    "Chronology": "כרונולוגיה",
    "Church history": "תולדות הכנסייה",
    "Civilization": "ציבילי��ציה תרבות",
    "Classification": "סיווג",
    "Commentaries": "פירושים",
    "Concordances": "קונקורדנציות",
    "Controversial literature": "ספרות פולמוסית",
    "Conversion to Christianity": "המרה לנצרות",
    "Correspondence": "התכתבות מכתבים",
    "Court and courtiers": "חצר וחצרנים",
    "Criticism and interpretation": "ביקורת ופרשנות",
    "Criticism, Textual": "ביקורת טקסטואלית",
    "Criticism, interpretation, etc": "ביקורת ופרשנות",
    "Customs and practices": "מנהגים",
    "Death and burial": "מוות וקבורה",
    "Description and travel": "תיאור ו��סעות",
    "Designs and plans": "תכניות",
    "Diaries": "יומנים",
    "Dictionaries": "מילונים",
    "Discovery and exploration": "גילוי וחקירה",
    "Doctrines": "דוקטרינות תורות",
    "Drama": "דרמה",
    "Early church, ca. 30-600": "הכנסייה הקדומה",
    "Economic aspects": "היבטים כלכליים",
    "Economic conditions": "תנאים כלכליים",
    "Economic policy": "מדיניות כלכלית",
    "Emancipation": "אמנציפציה שחרור",
    "Encyclopedias": "אנציקלופדיות",
    "Ethics": "אתיקה",
    "Etymology": "אטימולוגיה",
    "Exhibitions": "תערוכות",
    "Fables": "משלים",
    "Facsimiles": "פקסימיליות העתקים",
    "Fiction": "סיפורת בדיון",
    "First editions": "מהדורות ראשונות",
    "Folklore": "פולקלור",
    "Foreign elements": "יסודות זרים",
    "Foreign relations": "יחסי חוץ",
    "Forgeries": "זיופים",
    "Friends and associates": "ידידים ועמיתים",
    "Genealogy": "גנאלוגיה יוחסין",
    "Geography": "גיאוגרפיה",
    "Glossaries, vocabularies, etc": "אוצרות מילים",
    "Grammar": "דקדוק",
    "Grammar, Comparative": "דקדוק השוואתי",
    "Guidebooks": "מדריכים",
    "Handbooks, manuals, etc": "מדריכים",
    "Historiography": "��יסטוריוגרפיה",
    "History": "היסטוריה תולדות",
    "History and criticism": "היסטוריה וביקורת",
    "History of Biblical events": "היסטוריה של אירועי המקרא",
    "History, Military": "היסטוריה צבאית",
    "Illustrations": "איורים",
    "Imprints": "דפוסים",
    "In art": "באמנות",
    "Indexes": "מפתחות",
    "Intellectual life": "חיי רוח",
    "Introductions": "מבואות",
    "Islam": "אסלאם",
    "Judaism": "יהדות",
    "Knowledge and learning": "ידע ולימוד",
    "Language, style": "שפה וסגנון",
    "Languages": "שפות",
    "Law and legislation": "חוק וחקיקה",
    "Legal status, laws, etc": "מעמד משפטי",
    "Legends": "אגדות מסורות",
    "Library": "ספרייה",
    "Literary collections": "לקטים ספרותיים",
    "Liturgy": "ליטורגיה תפילה פולחן",
    "Manuscript": "כתב יד",
    "Manuscripts": "כתבי יד",
    "Methodology": "מתודולוגיה",
    "Military leadership": "מנהיגות צבאית",
    "Miscellanea": "שונות",
    "Mythology": "מיתולוגיה",
    "Onomasticon": "אונומסטיקון שמות",
    "Orders": "מסדרים",
    "Origin": "מקור",
    "Origin and antecedents": "מקורות והקדמות",
    "Paraphrases": "פרפרזות",
    "Passion": "פסיון",
    "Periodicals": "כתבי עת",
    "Persecutions": "רדיפות",
    "Personal narratives": "עדויות אישיות",
    "Philosophy": "פילוסופיה",
    "Pictorial works": "עבודות ציוריות",
    "Poetry": "שירה",
    "Political and social views": "השקפות פוליטיות וחברתיות",
    "Politics and government": "פוליטיקה ושלטון",
    "Portraits": "דיוקנאות",
    "Prayers and devotions": "תפילות",
    "Prices": "מחירים",
    "Psychology": "פסיכולוגיה",
    "Quotations": "ציטוטים",
    "Readers": "ספרי קריאה",
    "Relations": "יחסים",
    "Religion": "דת",
    "Religious aspects": "היבטים דתיים",
    "Religious life and customs": "חיי דת ומנהגים",
    "Romances": "רומנסות",
    "Scores": "פרטיטורות",
    "Sephardic rite": "מנהג ספרד נוסח ספרד",
    "Sermons": "דרשות",
    "Social conditions": "תנאים חברתיים",
    "Social life and customs": "חיי חברה ומנהגים",
    "Societies, etc": "אגודות",
    "Sources": "מקורות",
    "Specimens": "דוגמאות",
    "Study and teaching": "לימוד והוראה",
    "Style": "סגנון",
    "Technique": "טכניקה",
    "Textbooks": "ספרי לימוד",
    "Textbooks for foreign speakers": "ספרי לימוד ל��וברי שפות זרות",
    "Texts": "טקסטים נוסחים",
    "Themes, motives": "נושאים ומוטיבים",
    "Theology": "תיאולוגיה",
    "Translating": "תרגום",
    "Trials, litigation, etc": "משפטים",
    "Verb": "פועל",
    "Versification": "חריזה",
    "Versions": "גרסאות נוסחאות",
    "Vocalization": "ניקוד",
    "Vulgate": "וולגטה",
    "Writing": "כתיבה",
    # ── Translations ─────────────────────────────────────────────────────
    "Translations from Hebrew": "תרגומים מעברית",
    "Translations into Dutch": "תרגומים להולנדית",
    "Translations into English": "תרגומים לאנגלית",
    "Translations into French": "תרגומים לצרפתית",
    "Translations into German": "תרגומים לגרמנית",
    "Translations into Hebrew": "תרגומים לעברית",
    "Translations into Italian": "תרגומים לאיטלקית",
    "Translations into Latin": "תרגומים ללטינית",
    # ── Languages as subdivisions ────────────────────────────────────────
    "Arabic": "ערבית",
    "Aramaic": "ארמית",
    "Dutch": "הולנדית",
    "English": "אנגלית",
    "Ethiopic": "אתיופית געז",
    "French": "צרפתית",
    "German": "גרמנית",
    "Greek": "יוונית",
    "Hebrew": "עברית",
    "Italian": "איטלקית",
    "Ladino": "לדינו",
    "Latin": "לטינית",
    "Polyglot": "רב-לשוני",
    "Portuguese": "פורטוגזית",
    "Spanish": "ספרדית",
    "Syriac": "סורית",
    "Yiddish": "אידיש",
    # ── Geographic subdivisions ──────────────────────────────────────────
    "Alsace": "אלזס",
    "Amsterdam": "א��סטרדם",
    "Arab countries": "ארצות ערב",
    "Augsburg": "אוגסבורג",
    "Austria": "אוסטריה",
    "Belgium": "בלגיה",
    "Berlin": "ברלין",
    "Brazil": "ברזיל",
    "Brittany": "ברטאן",
    "China": "סין",
    "Cologne": "קלן",
    "Czech Republic": "צ'כיה",
    "Denmark": "דנמרק",
    "Egypt": "מצרים",
    "England": "אנגליה",
    "Eretz Israel": "ארץ ישראל",
    "Ethiopia": "אתיופיה",
    "Europe": "אירופה",
    "Florence": "פירנצה",
    "France": "צרפת",
    "Frankfurt am Main": "פרנקפורט",
    "Germany": "גרמניה",
    "Great Britain": "בריטניה",
    "Greece": "יוון",
    "Haarlem": "הארלם",
    "Holy Roman Empire": "האימפריה הרומית הקדושה",
    "Hungary": "הונגריה",
    "India": "הודו",
    "Ingolstadt": "אינגולשטט",
    "Ireland": "אירלנד",
    "Israel": "ישראל",
    "Italy": "איטליה",
    "Japan": "יפן",
    "Jerusalem": "ירושלים",
    "Korea": "קוריאה",
    "Lausanne": "לוזאן",
    "Lille": "ליל",
    "Lithuania": "ליטא",
    "London": "לונדון",
    "Mantua": "מנטובה",
    "Milan": "מילאנו",
    "Modena": "מודנה",
    "Netherlands": "הולנד",
    "New Orleans": "ניו אורלינס",
    "Odessa": "אודסה",
    "Padua": "פדובה",
    "Paris": "פריז",
    "Pavia": "פאוויה",
    "Poland": "פולין",
    "Portugal": "פורטוגל",
    "Prussia": "פ��וסיה",
    "Rome": "רומא",
    "Russia": "רוסיה",
    "Saint Helena": "סנט הלנה",
    "Scotland": "ס��וטלנד",
    "Siena": "סיינה",
    "Soviet Union": "ברית המועצות",
    "Spain": "ספרד",
    "Sweden": "שוודיה",
    "Switzerland": "שוויץ",
    "Tomar": "תומאר",
    "United States": "ארצות הברית",
    "Utrecht": "אוטרכט",
    "Venice": "ונציה",
    "Vienna": "וינה",
    "Yemen": "תימן",
    "Zurich": "ציריך",
    # ── Bible books as subdivisions ──────────────────────────────────────
    "Daniel": "דניאל",
    "Deuteronomy": "דברים",
    "Ecclesiastes": "קהלת",
    "Esther": "אסתר",
    "Exodus": "שמות",
    "Ezekiel": "יחזקאל",
    "Five Scrolls": "חמש מגילות",
    "Genesis": "בראשית",
    "Gospels": "הבשורות",
    "Hagiographa": "כתובים",
    "Isaiah": "ישעיהו",
    "Jeremiah": "ירמיהו",
    "Job": "איוב",
    "Leviticus": "ויקרא",
    "Minor Prophets": "תרי עשר",
    "New Testament": "הברית החדשה",
    "Numbers": "במדבר",
    "Old Testament": "תנ\"ך",
    "Pentateuch": "חומש תורה",
    "Prophets": "נביאים",
    "Proverbs": "משלי",
    "Psalms": "תהילים",
    "Ruth": "רות",
    "Samuel": "שמואל",
    "Song of Songs": "שיר השירים",
    "Later prophets": "נביאים אחרונים",
    # ── Talmud / Mishnah subdivisions ──────────────────────────��─────────
    "Berakhot": "ברכות",
    "Ketubbot": "כתובות",
    "Onkelos": "אונקלוס",
    "Shulhan arukh": "שולחן ערוך",
    # ── Century / period subdivisions ────────────────────────────────────
    "11th century": "המאה ה-11",
    "12th century": "המאה ה-12",
    "13th century": "המאה ה-13",
    "13th cent": "המאה ה-13",
    "14th century": "המאה ה-14",
    "15th century": "המאה ה-15",
    "15th and 16th centuries": "המאות ה-15 וה-16",
    "16th century": "המאה ה-16",
    "17th century": "המאה ה-17",
    "18th century": "המאה ה-18",
    "19th century": "המאה ה-19",
    "20th century": "המאה ה-20",
    "Early modern, 1500-1700": "ראשית העת החדשה",
    "Early works to 1700": "כתבים מוקדמים עד 1700",
    "Early works to 1800": "כתבים מוקדמים עד 1800",
    "Early works to 1900": "כתבים מוקדמים עד 1900",
    "Middle Ages, 500-1500": "ימי הביניים",
    "Middle Ages, 600-1500": "ימי הביניים",
    "Middle English, 1100-1500": "אנגלית תיכונה",
    "Pre-Linnean works": "כתבים טרום-לינאיים",
    "To 1500": "עד 1500",
    "To 400": "עד 400",
    "To 500": "עד 500",
    "To 70 A.D": "עד 70 ל��פירה",
    "Works to 1900": "כתבים עד 1900",
    # ── Historical events as subdivisions ────────────────────��───────────
    "Captivity, 1815-1821": "שבי",
    "Civil War, 1861-1865": "מלחמת האזרחים",
    "Fourth, 1202-1204": "הרביעי",
    "French occupation, 1798-1801": "הכיבו�� הצרפתי",
    "Rebellion, 66-73": "המרד הגדול",
    "Revolution, 1789-1799": "המהפכה הצרפתית",
    "Siege, 1203-1204": "מצור",
    "Wars of the Huguenots, 1562-1598": "מלחמות ההוגנוטים",
    "Napoleonic Conquest, 1808-1813": "הכיבוש הנפוליאוני",
    # ── Misc frequent subdivisions ───────────────────────────────────────
    "Catholic Church": "הכנסייה הקתולית",
    "Catholic authors": "מחברים קתוליים",
    "Jewish authors": "מחברים יהודים",
    "Kings and rulers": "מלכים ושליטים",
    "Anatomy": "אנטומ��ה",
}

# =============================================================================
# FULL OVERRIDES — subjects that need non-compositional translation
# =============================================================================
FULL_OVERRIDES: dict[str, str] = {
    # The subjects below don't decompose well or need special handling
    "Limited editions": "מהדור��ת מצומצמות",
    "Napoléon -- I, -- Emperor of the French, -- 1769-1821.":
        "נפוליאון הראשון קיסר צרפת",
    "Napoléon -- I, -- Emperor of the French, -- 1769-1821 -- Captivity, 1815-1821.":
        "נפוליאון הראשון שבי",
    "Napoléon -- I, -- Emperor of the French, -- 1769-1821 -- Egyptian campaign, 1798-1799.":
        "נפוליאון הראשון המסע המצרי",
    "Waterloo, Battle of, Waterloo, Belgium, 1815":
        "קרב ווטרלו",
    "Prayers -- Judaism": "תפילות ביהדות תפילה יהודית",
    "Caro, Yosef ben Efrayim, -- 1488-1575. -- Shulhan arukh.":
        "קארו יוסף בן אפרים שולחן ערוך",
    "Bible. -- Old Testament -- Hebrew -- Texts":
        "תנ\"ך עברית נוסחים",
    "Bible. -- Pentateuch -- Commentaries.":
        "חומש תורה פירושים",
    "Bible. -- Pentateuch -- Commentaries":
        "חומש תורה פירושים",
    "Bible. -- Psalms -- Commentaries.":
        "תהילים פירושים",
    "Bible -- Texts": "תנ\"ך נוסח��ם טקסטים",
    "Bible -- Commentaries.": "תנ\"ך פירושים",
    "Bible -- Commentaries": "תנ\"ך פירושים",
    "Rashi, -- 1040-1105 -- Criticism and interpretation":
        "רש\"י שלמה יצחקי ביקורת ופרשנות",
    "Jewish liturgy -- Texts": "ליטורגיה יהודית תפילה פולחן ��וסחים",
    "Judaism -- Liturgy -- Texts": "יהדות ליטורגיה תפילה פולחן נוסחים",
    "Judaism -- Periodicals": "יהדות כתבי עת",
    "Mishnah -- Commentaries.": "משנה פירושים",
    "Hebrew language -- Grammar -- Early works to 1800.":
        "עברית דקדוק כתבים מוקדמים",
    "Hebrew language -- Grammar -- Early works to 1800":
        "עברית דקדוק כתבים מוקדמים",
    "Hebrew language -- Grammar": "עברית דקדוק",
    "Hebrew language -- Accents and accentuation -- Early works to 1800":
        "עברית ניקוד וטעמים",
    "Talmud Bavli.": "תלמוד בבלי",
    "Masorah.": "מסורה",
    "Zohar.": "זוהר",
    "Piyyutim": "פיוטים פיוט",
    "Manuscripts, Ethiopic.": "כתבי יד אתיופיים",
    "Ethiopic literature -- Jewish authors": "ספרות אתיופית מחברים יהודים",
    "Jews, Ethiopian": "יהודי אתיופיה ביתא ישראל פלאשים",
    "Incunabula -- Facsimiles": "אינקונבולה דפוסי ערש העתקים",
    "Rare books -- Bibliography": "ספרים נד��רים ביבליוגרפיה",
    "Jewish ethics -- 14th century": "מוסר יהודי המאה ה-14",
    "Jewish ethics -- 17th century": "מוסר יהודי המאה ה-17",
    "Jewish ethics -- 18th century.": "מוסר יהודי המאה ה-18",
    "Cabala -- History -- 16th century.": "קבלה היסטוריה המאה ה-16",
    "Jewish philosophy -- Middle Ages, 500-1500.":
        "פילוס��פיה יהודית מחשבת ישראל ימי הביניים",
    "Responsa -- 16th century": "שו\"ת תשובות המאה ה-16",
    "Responsa -- 17th century.": "שו\"ת תשובות המאה ה-17",
    "Printing -- Poetry": "דפוס שירה",
    "Printing -- Specimens": "דפוס דוגמאות",
    "Printing -- History": "תולדות הדפוס היסטוריה של הדפוס",
    "Printing -- History -- Origin and antecedents":
        "תולדות הדפוס מקורות",
    "Eretz Israel -- Description and travel.": "ארץ ישראל תיאור ומסעות",
    "Jews -- History -- Sources.": "יהודים היסטוריה מקורות",
    "Jews -- History": "יהודים היסטוריה תולדות",
    "Jews -- Antiquities": "יהודים עתי��ות",
    "Mary -- (New Testament figure) -- Prayers and devotions.":
        "מריה תפילות",
    "Moses -- (Biblical leader)": "משה רבנו",
    "Napoleonic Wars, 1800-1815 -- Campaigns -- Russia":
        "מלחמות נפוליאון מסעות מלחמה רוסיה",
    "Napoleonic Wars, 1800-1815 -- Campaigns":
        "מלחמות נפוליאון מסעות מלחמה",
    "France -- History -- Consulate and First Empire, 1799-1815":
        "צרפת היסטוריה הקונסוליה והאימפריה הראשונה",
    "Catholic Church -- Liturgy -- Texts -- Bibliography.":
        "הכנסייה הקתולית ליטורגיה",
    "Catholic Church -- Liturgy -- Texts.":
        "הכנסייה הקתולית ליטורגיה נוסחים",
    "Catholic Church -- Prayers and devotions -- French.":
        "הכנסייה הקתולית תפילות צרפתית",
    "Fasts and feasts -- Judaism -- Liturgy -- Texts":
        "צומות וחגים יהדות ליטורגיה תפילה",
    "Fables, Hebrew": "משלים עבריים",
    "Hoshana Rabba -- Liturgy -- Texts":
        "הושענא רבה ליטורגיה תפילה נוסחים",
    "Jewish liturgy -- France -- Texts":
        "ליטורגיה יהודית תפילה צרפת נוסחים",
    "Jewish liturgy -- Italy -- Texts":
        "ליטורגיה יהודית תפילה איטליה נוסחים",
    "Jewish liturgy -- Jerusalem -- Texts":
        "ליטורגיה יהודית תפילה ירושלים נוסחים",
    "Jewish liturgy -- Texts":
        "ליטורגיה יהודית תפילה פולחן נוסחים",
    "Bookbinding -- Facsimiles": "כריכת ספרים העתקים",
    "Bookplates, Russian": "תוויות ספרים רוסיות",
    "Book ornamentation": "עיטור ספרים קישוט ספרים",
    "Comedy": "קומדיה",
    "Commandments (Judaism)": "מצוות",
    "Dance of death": "ריקוד המוות",
    "Ethiopian rite (Catholic Church)": "הנוסח האתיופי כנסייה קתולית",
    "Ethiopic book of Enoch.": "ספר חנוך האתיופי",
    "Ezra -- (Biblical figure)": "עזרא",
    "Enoch -- (Biblical figure)": "חנוך",
    "Illustrated books": "ספרים מאוירים",
    "Jewish astronomy": "אסטרונומיה יהודית תכונה",
    "Jewish question": "השאלה היהודית",
    "Jewish Science": "מדע יהודי",
    "Jewish wit and humor": "הומור יהודי",
    "Knowledge, Theory of": "תורת הידע אפיסטמולוגיה",
    "Language and languages": "שפה ושפות",
    "Satire, French": "סטירה צרפתית",
    "Satire, Latin": "סטירה לטינית",
    "Selichot": "סליחות",
    "Tragedies (Drama)": "טרגדיות",
    "Benediction (Jewish law)": "ברכות ברכה",
    "Berit milah.": "ברית מילה",
    "Baruch ben Neriah.": "ברוך בן נריה",
    "Agency (Jewish law)": "שליחות הלכה",
    "Agricultural laws and legislation (Jewish law)": "חוקי חקלאות הלכה",
    "Bible as literature": "המקרא ��ספרות",
    "Blessing and cursing in the Bible.": "ברכה וקללה במקרא",
    "Absurdist drama": "דרמה אבסורדית",
    "Alphabets": "אלפביתים",
    "Arabic wit and humor": "הומור ערבי",
    "Authorship": "כתיבה ��יבור",
    "Best books": "ספרים מומלצים",
    "Books in art": "ספרים באמנות",
    "Book selection": "בחירת ספרים",
    "Acre (Israel)": "עכו",
    "Authors and readers": "מחברים וקוראים",
    "Authors, Yiddish": "סופרים ביידיש",
    "Yiddish fiction": "סיפורת אידיש",
    "Hebrew fiction -- 20th century": "סיפורת עברית המאה ה-20",
    "Hebrew poetry -- 20th century": "שירה עברית המאה ה-20",
    "Hebrew poetry, Medieval": "שירה עברית ימי הביניים",
    "French poetry -- 18th century": "שירה צרפתית המאה ה-18",
    "French poetry -- 19th century": "שירה צרפתית המאה ה-19",
    "French poetry -- 20th century": "שירה צרפתית המאה ה-20",
    "German poetry -- 20th century": "שירה גרמנית המאה ה-20",
    "Hebrew poetry": "שירה עברית",
    "Apocrypha. -- Ethiopic -- Versions.":
        "ספרים חיצוניים אתיופית גרסאות",
    "Ethiopian literature": "ספרות אתיופית",
    "Ethiopic literature": "ספרות אתיופית",
}


# =============================================================================
# Translation logic
# =============================================================================

def translate_subject(value: str) -> str | None:
    """Translate a single subject value to Hebrew.

    Returns None if no translation is available.
    """
    # Strip trailing period for lookup (LCSH often has trailing dots)
    clean = value.rstrip(".")

    # 1. Check full overrides first (both with and without trailing period)
    if value in FULL_OVERRIDES:
        return FULL_OVERRIDES[value]
    if clean in FULL_OVERRIDES:
        return FULL_OVERRIDES[clean]

    # 2. Check base translations for simple (non-subdivided) subjects
    if clean in BASE_TRANSLATIONS:
        return BASE_TRANSLATIONS[clean]

    # 3. Component-based: split on " -- " and translate each part
    parts = [p.strip().rstrip(".") for p in value.split(" -- ")]
    translated_parts = []
    any_translated = False

    for i, part in enumerate(parts):
        # Try base translations for first part, subdivision for rest
        lookup = BASE_TRANSLATIONS if i == 0 else SUBDIVISION_TRANSLATIONS
        if part in lookup:
            translated_parts.append(lookup[part])
            any_translated = True
        elif part in BASE_TRANSLATIONS:
            # Subdivision might also be a base term
            translated_parts.append(BASE_TRANSLATIONS[part])
            any_translated = True
        elif part in SUBDIVISION_TRANSLATIONS:
            translated_parts.append(SUBDIVISION_TRANSLATIONS[part])
            any_translated = True
        else:
            # Check if it's a date/period pattern — skip these
            if re.match(r"^\d{2,4}", part) or re.match(r"^ca\.", part):
                translated_parts.append("")  # Skip dates in Hebrew
            else:
                translated_parts.append("")  # No translation available

    if not any_translated:
        return None

    # Join non-empty parts with spaces (for FTS searchability)
    result = " ".join(p for p in translated_parts if p)
    return result.strip() or None


def run(*, dry_run: bool = False) -> dict:
    """Add Hebrew translations to subjects table and rebuild FTS."""
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")

    # --- Step 1: Add value_he column if not exists ---
    cols = [r[1] for r in conn.execute("PRAGMA table_info(subjects)").fetchall()]
    if "value_he" not in cols:
        if not dry_run:
            conn.execute("ALTER TABLE subjects ADD COLUMN value_he TEXT")
            conn.commit()
        print("Added value_he column to subjects table")

    # --- Step 2: Load all distinct subjects ---
    rows = conn.execute(
        "SELECT DISTINCT value FROM subjects"
    ).fetchall()
    values = [r[0] for r in rows]
    print(f"Total distinct subjects: {len(values)}")

    # --- Step 3: Translate ---
    translations: dict[str, str] = {}
    skipped = 0
    for v in values:
        he = translate_subject(v)
        if he:
            translations[v] = he
        else:
            skipped += 1

    print(f"Translated: {len(translations)}, Skipped: {skipped}")
    print(f"Coverage: {len(translations) / len(values) * 100:.1f}%")

    if dry_run:
        # Show sample
        print("\n--- Sample translations (first 30) ---")
        for eng, heb in list(translations.items())[:30]:
            print(f"  {eng}")
            print(f"    → {heb}")
        conn.close()
        return {
            "translated": len(translations),
            "skipped": skipped,
            "coverage_pct": round(len(translations) / len(values) * 100, 1),
        }

    # --- Step 4: Drop FTS triggers BEFORE bulk update ---
    conn.execute("DROP TRIGGER IF EXISTS subjects_fts_insert")
    conn.execute("DROP TRIGGER IF EXISTS subjects_fts_delete")
    conn.execute("DROP TRIGGER IF EXISTS subjects_fts_update")
    conn.execute("DROP TABLE IF EXISTS subjects_fts")
    conn.commit()
    print("Dropped old FTS triggers and table")

    # --- Step 5: Bulk update subjects with Hebrew translations ---
    updated = 0
    for eng_value, he_value in translations.items():
        cur = conn.execute(
            "UPDATE subjects SET value_he = ? WHERE value = ?",
            (he_value, eng_value),
        )
        updated += cur.rowcount
    conn.commit()
    print(f"Updated {updated} subject rows with Hebrew translations")

    # --- Step 6: Rebuild FTS with bilingual content ---
    conn.execute("""
        CREATE VIRTUAL TABLE subjects_fts USING fts5(
            mms_id,
            value,
            content=''
        )
    """)
    conn.execute("""
        INSERT INTO subjects_fts(rowid, mms_id, value)
        SELECT s.id, r.mms_id,
               s.value || ' ' || COALESCE(s.value_he, '')
        FROM subjects s
        JOIN records r ON r.id = s.record_id
    """)

    # Recreate triggers to include Hebrew in FTS
    conn.execute("""
        CREATE TRIGGER subjects_fts_insert AFTER INSERT ON subjects BEGIN
            INSERT INTO subjects_fts(rowid, mms_id, value)
            SELECT NEW.id, r.mms_id,
                   NEW.value || ' ' || COALESCE(NEW.value_he, '')
            FROM records r WHERE r.id = NEW.record_id;
        END
    """)
    conn.execute("""
        CREATE TRIGGER subjects_fts_delete AFTER DELETE ON subjects BEGIN
            DELETE FROM subjects_fts WHERE rowid = OLD.id;
        END
    """)
    conn.execute("""
        CREATE TRIGGER subjects_fts_update AFTER UPDATE ON subjects BEGIN
            DELETE FROM subjects_fts WHERE rowid = OLD.id;
            INSERT INTO subjects_fts(rowid, mms_id, value)
            SELECT NEW.id, r.mms_id,
                   NEW.value || ' ' || COALESCE(NEW.value_he, '')
            FROM records r WHERE r.id = NEW.record_id;
        END
    """)
    conn.commit()
    print("Rebuilt subjects_fts with bilingual content")

    conn.close()
    return {
        "translated": len(translations),
        "skipped": skipped,
        "updated_rows": updated,
        "coverage_pct": round(len(translations) / len(values) * 100, 1),
    }


if __name__ == "__main__":
    import sys
    dry = "--dry-run" in sys.argv
    result = run(dry_run=dry)
    print(f"\nResult: {result}")
