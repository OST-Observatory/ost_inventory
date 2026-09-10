#!/usr/bin/env python3
"""Convert the LibreOffice HTML inventory export into an import CSV."""

from __future__ import annotations

import csv
import re
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "data" / "inventory _list.html"
OUTPUT = ROOT / "data" / "inventory_import.csv"
MAX_FIELD = 500
MAX_CATS = 4

SECTION_CATEGORY = {
    "Adapter": "Adapter",
    "Schrauben": "Hardware",
    "Akkus und Batterien": "Battery",
    "Computer": "Computer",
    "Computertechnik": "Computing",
    "Fernbedienungen": "Hand controller",
    "Filter": "Filter",
    "Handbücher": "Manual",
    "Software": "Software",
    "Helferlein": "Accessory",
    "Infomationsmaterial": "Outreach",
    "Büromaterialien": "Office",
    "Schlüssel": "Keys",
    "Kabel": "Cable",
    "Kameras": "Camera",
    "Kamerazubehör": "Camera accessory",
    "Kameraobjektiv": "Camera lens",
    "Koffer und Taschen": "Case",
    "Leuchtmittel": "Lighting",
    "Linsen": "Optics",
    "Netzteile": "Power supply",
    "Okular": "Eyepiece",
    "Organisation": "Furniture",
    "Praesentation": "Outreach",
    "Reinigung": "Cleaning",
    "Sonnenfilter": "Solar",
    "Spektrographen": "Spectrograph",
    "Stative": "Tripod",
    "Teleskope": "Telescope",
    "Teleskopteile": "Telescope part",
    "Telescope tools": "Tool",
    "Montierung": "Mount",
    "Unterlagen": "Documents",
    "Werkzeug": "Tool",
    "Elektro-Bastelzeug": "Electronics",
    "Bauprojekt: Florian – Monitoring": "Electronics",
    "Bauprojekt: Rainer – Mount": "Electronics",
    "Bauprojekt: 21MHz Radioteleskop": "Radio",
    "Bauprojekt: Radio tools": "Radio",
    "Bauprojekt: Sol’Ex": "Solar",
}

SECTION_PROJECT = {
    "Bauprojekt: Florian – Monitoring": "Monitoring (Florian)",
    "Bauprojekt: Rainer – Mount": "Mount (Rainer)",
    "Bauprojekt: 21MHz Radioteleskop": "21 MHz radio telescope",
    "Bauprojekt: Radio tools": "Radio tools",
    "Bauprojekt: Sol’Ex": "Sol'Ex",
}

CAT_MAP = {
    "adapter": "Adapter",
    "kabel": "Cable",
    "teleskopteile": "Telescope part",
    "helferlein": "Accessory",
    "elektro-bastelzeug": "Electronics",
    "elektronik": "Electronics",
    "werkzeug": "Tool",
    "filter": "Filter",
    "kamera": "Camera",
    "kameras": "Camera",
    "handbuch": "Manual",
    "schrauben": "Hardware",
    "teleskop": "Telescope",
    "teleskope": "Telescope",
    "computertechnik": "Computing",
    "netzteile": "Power supply",
    "netzteil": "Power supply",
    "buromaterialien": "Office",
    "büromaterialien": "Office",
    "leuchtmittel": "Lighting",
    "gluehbirne": "Lighting",
    "led-birne": "Lighting",
    "halogenlampe": "Lighting",
    "strahler": "Lighting",
    "c8": "C8",
    "qhy600m": "QHY600M",
    "reinigung": "Cleaning",
    "konservierungsmittel": "Cleaning",
    "wartung": "Cleaning",
    "rasa": "RASA",
    "canon 700d": "Canon 700D",
    "okulare": "Eyepiece",
    "okular": "Eyepiece",
    "apo": "APO",
    "ts apo": "APO",
    "photoline 130 apo": "APO",
    "eingefasster filter": "Filter",
    "uneingefasst filter": "Filter",
    "50mm": None,
    "linsen": "Optics",
    "linse": "Optics",
    "barlow linse": "Optics",
    "dados": "DADOS",
    "qhy268m": "QHY268M",
    "c11 / c14": "C11",
    "c12 / c14": "C14",
    "c11": "C11",
    "c14": "C14",
    "baches": "BACHES",
    "cdk20": "CDK20",
    "cdk 20": "CDK20",
    "teleskop ost": "CDK20",
    "ost teleskop": "CDK20",
    "koffer und taschen": "Case",
    "computer": "Computer",
    "pc": "Computer",
    "pc ost": "Computer",
    "ufc": "UFC",
    "1 1/4\"": '1.25"',
    "1 ¼”": '1.25"',
    "1 ¼\"": '1.25"',
    "2”": '2"',
    "2\"": '2"',
    "sonnenfilter": "Solar",
    "filterbrillen": "Solar",
    "sun": "Solar",
    "akkus und batterien": "Battery",
    "akku": "Battery",
    "stf 8300": "STF-8300",
    "stf8300m": "STF-8300",
    "raspberry pi": "Raspberry Pi",
    "software": "Software",
    "sucherfernrohr": "Finderscope",
    "montierung": "Mount",
    "spektrographen": "Spectrograph",
    "spektrograph": "Spectrograph",
    "st-7/8": "ST-7/8",
    "st-7 und st-8": "ST-7/8",
    "all-sky-kamera": "All-sky",
    "sbig-allsky-340-kamera": "All-sky",
    "qhycfw3xl": "Filter wheel",
    "qhycfw3l": "Filter wheel",
    "rcu": "RCU",
    "kalibration": "Calibration",
    "praesentation": "Outreach",
    "informationsmaterial": "Outreach",
    "stative": "Tripod",
    "stativ": "Tripod",
    "reduzierung": "Reducer",
    "gm4000 qci": "GM4000",
    "hpsii4000": "GM4000",
    "kamerazubehör": "Camera accessory",
    "kameraobjektiv": "Camera lens",
    "organisation": "Furniture",
    "unterlagen": "Documents",
    "logbuch": "Documents",
    "stop ring": "Adapter",
    "ring": "Adapter",
    "fokussiereinrichtung": "Focuser",
    "fokussierhilfe": "Focuser",
    "software handbuch": "Manual",
    "software handbuch + download": "Manual",
    "teleskop handbuch": "Manual",
    "cgx-l, cge-pro, advanced gt": "Mount",
    "radioschüssel": "Radio",
    "sdr": "Radio",
    "telescope tools": "Tool",
    "messen": "Measuring",
    "kamera adapter": "Adapter",
    "camera adapter": "Adapter",
    "90 grad umlenkspiegel": "Diagonal",
    "winkel 90 grad": "Diagonal",
    "praktikum": "Lab course",
    "vr": "VR",
    "temperatur modul": "Electronics",
    "aktive optik": "Active optics",
    "schlüssel": "Keys",
    "zwo asi174mm mini": "ZWO",
    "kuppel": "Dome",
    "dome": "Dome",
    "coronado": "Coronado",
    "skyscout": "SkyScout",
    "eq8": "EQ8",
    "rechungen, vorschläge ost…": "Documents",
    "finetuning": "Adapter",
    "flatfieldfolie": "Flat field",
    "fernbedienungen": "Hand controller",
    "baches (verbaut)": "BACHES",
    "qhy268m, qhy600m": "QHY600M",
}

# Drop as categories; keep the fact in comments when useful.
SKIP_CATS = {
    "ost",
    "verbaut",
    "ehemals am baches verbaut",
    "50mm",
}

NAME_KEYWORDS = [
    ("RASA", "RASA"),
    ("QHY600", "QHY600M"),
    ("QHY268", "QHY268M"),
    ("QHYCFW", "Filter wheel"),
    ("BACHES", "BACHES"),
    ("DADOS", "DADOS"),
    ("CDK20", "CDK20"),
    ("CDK 20", "CDK20"),
    ("700D", "Canon 700D"),
    ("C14", "C14"),
    ("C11", "C11"),
    ("C8", "C8"),
    ("Raspberry", "Raspberry Pi"),
    ("Arduino", "Electronics"),
    ("GM4000", "GM4000"),
    ("CGX-L", "CGX-L"),
    ("CGE-Pro", "CGE-Pro"),
    ("EQ8", "EQ8"),
    ("UFC", "UFC"),
    ("ZWO", "ZWO"),
    ("ST-7", "ST-7/8"),
    ("ST-8", "ST-7/8"),
    ("STF", "STF-8300"),
    ("PHOTOLINE", "APO"),
    ("APO", "APO"),
    ("Herschel", "Solar"),
    ("Solar", "Solar"),
    ("Sonnen", "Solar"),
    ("Seeker", "Finderscope"),
    ("Sky Surfer", "Finderscope"),
    ("EVOGUIDE", "Finderscope"),
    ("Finderscope", "Finderscope"),
    ("finderscope", "Finderscope"),
]

CONTAINER_MAP = {
    "adapter": "Adapters",
    "dslr tasche": "DSLR bag",
    "dlsr tasche": "DSLR bag",
    "okularkoffer": "Eyepiece case",
    "dados koffer": "DADOS case",
    "dadoskoffer": "DADOS case",
    "baches koffer": "BACHES case",
    "stf 8300m koffer": "STF-8300M case",
    "st-7/8 koffer": "ST-7/8 case",
    "tasche toughbook": "Toughbook bag",
    "canon eos 700d zubehör": "Canon EOS 700D accessories",
    "kabel": "Cables",
    "batterien": "Batteries",
    "kleine dose mit blauem deckel": "Small tin with blue lid",
    "schwarze box": "Black box",
    "stromversorgung...": "Power supply",
    "tasche c14": "C14 bag",
    "leuchtmittel i": "Lamps I",
    "leuchtmittel ii": "Lamps II",
    "sonnen-beob.-brillen": "Solar observing glasses",
    "bastelzeug planeten": "Planet crafts",
}

PHRASES = [
    ("Bedienungsanleitung", "User manual"),
    ("Gebrauchsanweisung", "User manual"),
    ("Abdeckkappe Kamera", "Camera dust cap"),
    ("Teleskopschiene", "Telescope dovetail bar"),
    ("Schwalbenschwanzschiene und Adapterplatte", "Dovetail bar and adapter plate"),
    ("Schwalbenschwanz", "dovetail"),
    ("Umlenkprisma", "Star diagonal (prism)"),
    ("Umlenkspiegel", "Star diagonal (mirror)"),
    ("Okularklemme", "Eyepiece clamp"),
    ("Okluarklemme", "Eyepiece clamp"),
    ("Standardokularkleme", "Standard eyepiece clamp"),
    ("Abdeckungen für Okluar etc.", "Eyepiece covers"),
    ("Abdeckungen (alt) für Sky Surfer", "Sky Surfer covers (old)"),
    ("Abdeckung für den Router in der Kuppel", "Dome router cover"),
    ("Gummi Augenmuschel", "Rubber eyecup"),
    ("Projektionsadapter für Okularprojektion", "Eyepiece projection adapter"),
    ("Celestron Handyhalterung für die Okulare", "Celestron smartphone eyepiece holder"),
    ("Undefinierter Adapter (mit 4 metallischen Oins an der Seite)", "Unidentified adapter (four metal pins on the side)"),
    ("Adapter für das Filterrad der STF8300 (Benutzung ohne Off axis guider)", "STF-8300 filter-wheel adapter"),
    ("Adapter für die STF8300 (Benutzung ohne Filterrad)", "STF-8300 adapter without filter wheel"),
    ("Blende für die ST7/8 mit Eintritsfenster (für den Betrieb der Kameras ohne Filterrad)", "ST-7/8 aperture mask with entrance window"),
    ("Halterung zum ranschrauben für die QHY600M (rot)", "Screw-on bracket for QHY600M (red)"),
    ("Adapter CGE-Pro/CGX-L auf Säule in der Kuppel samt Schrauben", "CGE-Pro/CGX-L pier adapter for the dome, with screws"),
    ("Adapter QHY-Schwalbenschwanz (QHY600M) auf M54", "QHY600M dovetail to M54 adapter"),
    ("S68/M68 Zeiss-Change-Ring für M68 Schnellwechsler", "S68/M68 Zeiss change ring for M68 quick changer"),
    ("USB-3-A → B, Spiralkabel", "USB 3 A-to-B coiled cable"),
    ("USB-2-A → B", "USB 2 A-to-B cable"),
    ("Rider clamp 3’’ / 60 – an Stronghold Tangentialneiger verbaut", 'Rider clamp 3" / 60'),
    ("Piggyback Mount - SCT - to fit the DSLR on the C8, C11, C14", "SCT piggyback mount for DSLR (C8, C11, C14)"),
    ("2.5‘‘-Steckhülse mit 2 7/16‘‘ Gewinde und Adapterplatte mit 6 Schraublöchern (gegenüberliegende Löcher haben einen Abstand von 7cm)", "2.5\" nosepiece with 2 7/16\" thread and 6-hole adapter plate"),
    ("2 Zoll Steckhülse mit Riffeln (Safety Kerfs) - Baader M48 Extension Tube 30mm / 2'' nose piece with Safety Kerfs", "Baader M48 extension tube 30 mm"),
    ("2'' Steckhülse für die QHY268M & QHY600M (M54 Gewinde)", "2\" nosepiece for QHY268M and QHY600M (M54)"),
    ("M3x8mm Schrauben", "M3×8 mm screws"),
    ("M3x14mm Schrauben", "M3×14 mm screws"),
    ("M3x24mm Schrauben", "M3×24 mm screws"),
    ("M3x28mm Schrauben", "M3×28 mm screws"),
    ("Madenschrauben", "Set screws"),
    ("Erdharken", "Ground stakes"),
    ("Zeltheringe", "Tent pegs"),
    ("Unterlegscheiben", "Washers"),
    ("Okularstellschrauben", "Eyepiece lock screws"),
    ("Okularstellschraube", "Eyepiece lock screw"),
    ("Schraubhaken mit Holzgwinde", "Screw hooks with wood thread"),
    ("Spannschloss", "Turnbuckle"),
    ("Karabinerhaken", "Carabiners"),
    ("Sechskantschrauben", "Hex bolts"),
    ("Sicherungsmuttern", "Lock nuts"),
    ("Muttern mit Sicherungsring", "Nuts with lock washer"),
    ("Muttern", "nuts"),
    ("Gewindestange", "Threaded rod"),
    ("Rohrschellen Gelenkrohrschellen", "Hinged pipe clamps"),
    ("Ösen", "Eye bolts"),
    ("Schrauben ehemals am C11 verbaut, schwarz", "Black screws formerly on the C11"),
    ("Ersatzakku Canon DSLR", "Spare Canon DSLR battery"),
    ("SD-Kartenleser (intern)", "Internal SD card reader"),
    ("Backupfestplatten", "Backup hard drives"),
    ("Wärmeleitpaste (Rest)", "Thermal paste (remainder)"),
    ("Apater serieller COM-Port auf USB-A", "Serial COM to USB-A adapter"),
    ("Apapter LAN auf seriellen COM-Port (RJ45 zu RS232 DB9)", "LAN to serial COM adapter (RJ45 to RS232 DB9)"),
    ("Apapter & Umschalter von Seriel auf USB (4 fach)", "Serial-to-USB adapter and switch (4-port)"),
    ("Celestron Programming Cabel", "Celestron programming cable"),
    ("Blenden PCIE Geäuse hinten", "PCIe rear-slot covers"),
    ("Neewer externer Kameraauslöser", "Neewer external camera shutter release"),
    ("Hand terminal GM4000 QCI (OST Kuppel) – defekt", "GM4000 QCI hand terminal (OST dome) — defective"),
    ("Hand terminal GM4000 QCI (OST Kuppel)", "GM4000 QCI hand terminal (OST dome)"),
    ("leere Filterhüllen", "Empty filter cases"),
    ("Anleitungen und Infomaterial zum Praktikum", "Lab-course instructions and information"),
    ("Infomaterial für das Praktikum und die Öffentlichkeitsarbeit", "Information material for the lab course and outreach"),
    ("Rechnunen und Lieferscheine", "Invoices and delivery notes"),
    ("Doppelseitigesklebeband", "Double-sided tape"),
    ("Gewebeband (weiß, schmall)", "Gaffer tape (white, narrow)"),
    ("Gewebeband (schwarz, breit)", "Gaffer tape (black, wide)"),
    ("Gewebeband (grün, schmall)", "Gaffer tape (green, narrow)"),
    ("Abklebeband (gelb, breit)", "Masking tape (yellow, wide)"),
    ("Paketklebeband", "Packing tape"),
    ("Klebeband", "Tape"),
    ("Selbstklebendes Klettband", "Self-adhesive Velcro"),
    ("Stecknadeln Poster", "Poster pins"),
    ("Superglue (Sekundenkleber)", "Superglue"),
    ("Schere", "Scissors"),
    ("Labeldrucker", "Label printer"),
    ("Nachfüllset für den Labeldrucker", "Label-printer refill set"),
    ("Stifte", "Pens"),
    ("Beobachterprotokolle", "Observing logs"),
    ("Styroporkugel", "Styrofoam ball"),
    ("Fingermalfarbe - Grundfraben", "Finger paint (primary colours)"),
    ("Fließ zum basteln von Planeten", "Felt for planet crafts"),
    ("Laminiergerät", "Laminator"),
    ("Laminierfolien", "Laminating pouches"),
    ("Schlüssel für die Schränke im Seminarraum", "Keys for the seminar-room cabinets"),
    ("Kabeltrommel", "Cable reel"),
    ("Steuerungskabel", "control cable"),
    ("Netzwerkkabel", "Network cable"),
    ("Glasfaserkabel", "Fibre-optic cable"),
    ("Stromversorgungskabel", "Power cable"),
    ("Verlängerungskabel", "Extension cable"),
    ("Verlägerungskabel", "Extension cable"),
    ("Outdoor Verteilersteckdose, 5fach, blau-schwarz", "Outdoor 5-way distribution socket, blue-black"),
    ("serielles COM-Port-Kabel", "Serial COM cable"),
    ("Verbindungskabel Montierung (CGE-Pro, CGX-L und Advanced GT) auf Zigarettenanzünder Auto", "Mount power cable (CGE-Pro, CGX-L, Advanced GT) to car cigarette lighter"),
    ("Steckerleiste", "Power strip"),
    ("Kabelverschraubungen", "Cable glands"),
    ("Verbindungskabelsolar", "Solar connection cable"),
    ("Antennenkabel - Koaxialkabel", "Antenna coaxial cable"),
    ("Displayportkabel Normal auf mini", "DisplayPort to Mini DisplayPort cable"),
    ("Kameratasche", "Camera bag"),
    ("schwarze Box", "Black box"),
    ("Tasche schwarz für das C11 und RASA", "Black bag for C11 and RASA"),
    ("Tasche rot für das C14", "Red bag for C14"),
    ("Alte Aurora-Flatfieldfolie für das C14 und kleiner", "Old Aurora flat-field panel for C14 and smaller"),
    ("Aurora-Flatfieldfolie für das CDK20 (50cmx50cm)", "Aurora flat-field panel for CDK20 (50×50 cm)"),
    ("Flat Field Generator (Flatfieldfolie) für das C14 und kleiner", "Flat-field generator for C14 and smaller"),
    ("Ersatzlampen Kuppel", "Spare dome lamps"),
    ("Schreibtischlampe", "Desk lamp"),
    ("Outdoor Lichterkette", "Outdoor fairy lights"),
    ("Baustrahler", "Work light"),
    ("Leuchtstoffröhre hängend", "Hanging fluorescent tube"),
    ("Ersatzbirne für DADOS-Kalibrationslampe, Shelyak Wolfram", "Spare bulb for DADOS calibration lamp, Shelyak tungsten"),
    ("Ersatzbirne für DADOS-Kalibrationslampe, Shelyak Ne/Ar", "Spare bulb for DADOS calibration lamp, Shelyak Ne/Ar"),
    ("Schlitzbetrachtungseinheit (Baader)", "Baader slit-viewing unit"),
    ("Fokalreducer (Celestron, Reducer/Corrector Lens f/6.3)", "Celestron focal reducer/corrector f/6.3"),
    ("Akkuladegerät Canon 700D", "Canon 700D battery charger"),
    ("Netzteil Kamera Canon 700D", "Canon 700D camera power supply"),
    ("Adapter Netzteil Kamera Canon 700D", "Canon 700D camera PSU adapter"),
    ("Netzteil Toughbook", "Toughbook power supply"),
    ("Netzteil GM4000 (Teleskop OST) DEFEKT", "GM4000 power supply (OST telescope) — defective"),
    ("Unterschiedliche Adapter für Netzteile", "Assorted power-supply adapters"),
    ("Raspberry Pi 4 Netzteil", "Raspberry Pi 4 power supply"),
    ("Raspberry Pi 5 Netzteil", "Raspberry Pi 5 power supply"),
    ("Ausziehschrank (Rollcontainer)", "Rolling drawer cabinet"),
    ("grosser Aluschrank", "Large aluminium cabinet"),
    ("Schreibtisch", "Desk"),
    ("Planetenbilder (laminiert)", "Planet pictures (laminated)"),
    ("Sonnenbilder (laminiert)", "Solar pictures (laminated)"),
    ("Ballons", "Balloons"),
    ("Planetenweg: Infoschilder und Modelle (nicht vollständig)", "Planet trail: info signs and models (incomplete)"),
    ("Transportable Leinwand", "Portable projection screen"),
    ("Besen mit Wasseranschluss", "Broom with water connection"),
    ("Kleiner Eimer", "Small bucket"),
    ("Feinoptische Reinigungsfluessigkeit (Optical Wonder)", "Baader Optical Wonder cleaning fluid"),
    ("Hartwachslackschutz", "Hard-wax paint protection"),
    ("Lappen (viele)", "Cloths (many)"),
    ("Mikrofaserhandschuhe", "Microfibre gloves"),
    ("Mikrofasertuecher (einige)", "Microfibre cloths (several)"),
    ("Schlauch", "Hose"),
    ("Schwaemme (einige)", "Sponges (several)"),
    ("Luftspray", "Air duster"),
    ("Flugrostentferner", "Flash-rust remover"),
    ("Blasebalk (schwarz)", "Blower bulb (black)"),
    ("Sonnenfilter", "Solar filter"),
    ("Sonnenschutzbrille", "Solar observing glasses"),
    ("Gitter (200 Line/mm)", "Grating (200 lines/mm)"),
    ("Gitter (900 Line/mm)", "Grating (900 lines/mm)"),
    ("Kamerastativ", "Camera tripod"),
    ("kleiner Dreifuß", "Small tripod"),
    ("Gegengewicht Teleskop (Ersatz)", "Spare telescope counterweight"),
    ("Gegengewicht Teleskop", "Telescope counterweight"),
    ("Sucherfernrohr", "Finderscope"),
    ("Teleskopstutzen mit Trockenmittel", "Telescope adapter with desiccant"),
    ("Kolimationsset für das CDK20 (Ronchi Adapter, Ronchi Spacer, Ronchi Okular)", "CDK20 collimation set (Ronchi adapter, spacer, eyepiece)"),
    ("Gegengewichtsset zur Feintarierung CDK20 (verbaut)", "CDK20 fine-balance counterweight set"),
    ("Gegengewichtsset zur Feintarierung CDK20", "CDK20 fine-balance counterweight set"),
    ("Handterminal für die CGX-L (Celestron “NexStar”)", "CGX-L NexStar hand controller"),
    ("Handterminal für die CGE-Pro (Celestron “NexStar”)", "CGE-Pro NexStar hand controller"),
    ("Handterminal für die Advanced GT", "Advanced GT hand controller"),
    ("Handterminal für den Fokusser des CDK20 (PlaneWave Instruments)", "CDK20 focuser hand controller (PlaneWave)"),
    ("Taukappe für das C14", "Dew shield for C14"),
    ("Gegengewicht für die Advanced GT", "Advanced GT counterweight"),
    ("Gegengewichtstange für die Advanced GT", "Advanced GT counterweight shaft"),
    ("Konterschraube und Okularteller für die Advanced GT", "Advanced GT lock screw and eyepiece tray"),
    ("Gegengewichtstange für die CGE-Pro", "CGE-Pro counterweight shaft"),
    ("Gegengewichte für die CGE-Pro, CGX-L, und EQ8-R Pro", "Counterweights for CGE-Pro, CGX-L and EQ8-R Pro"),
    ("Gegengewicht für die CGE-Pro, CGX-L, und EQ8-R Pro", "Counterweight for CGE-Pro, CGX-L and EQ8-R Pro"),
    ("Gegengewicht GM4000-QCI & GM4000 HPS", "GM4000-QCI and GM4000 HPS counterweight"),
    ("Load bearing wheel for the dome", "Dome load-bearing wheel"),
    ("Sucherschuh – universal – Radioschüssel", "Universal finder shoe — radio dish"),
    ("Astropraktikum (Ordner)", "Astronomy lab course (folder)"),
    ("Archiv Astropraktikum (Ordner)", "Astronomy lab-course archive (folders)"),
    ("Ordner historisches", "Historical folder"),
    ("Imbusschluesselset", "Hex-key set"),
    ("Imbusschluessel", "Hex key"),
    ("Imbusschlüssel", "Hex key"),
    ("Schraubendreher", "Screwdriver"),
    ("Schraubenzieherset", "Screwdriver set"),
    ("Schraubenzieher", "Screwdriver"),
    ("Metallschere", "Tin snips"),
    ("Holzspartel", "Wooden spatula"),
    ("Kabelbinder", "Cable ties"),
    ("Klettbänder", "Velcro straps"),
    ("Seitenschneider", "Side cutters"),
    ("Kontaktspray", "Contact spray"),
    ("Massband", "Measuring tape"),
    ("Maulschluesselset", "Open-ended spanner set"),
    ("Maulschluessel", "Open-ended spanner"),
    ("Ratschenset (Nusskasten; schwarze Box)", "Socket-ratchet set (black box)"),
    ("Schluessel (OMS & Kuppelschrank)", "Keys (OMS and dome cabinet)"),
    ("Zollstock", "Folding rule"),
    ("Heißluftlötstation + Zubehör", "Hot-air soldering station and accessories"),
    ("Entlötsaugpumpe", "Desoldering pump"),
    ("Isolierband", "Electrical tape"),
    ("Messingwolle mit Halter (1x) zum Lötspitzenreinigen", "Brass-wool soldering-tip cleaner with holder"),
    ("Seilklemmhülsen-Set", "Cable-swage sleeve set"),
    ("Seilklemmzange - Sewager & Wire Cutter", "Swaging and wire-cutting pliers"),
    ("Temperatursensor für Multimeter", "Multimeter temperature probe"),
    ("Flussmittel", "Flux"),
    ("Entlötlitze", "Desoldering braid"),
    ("Lötzinn", "Solder"),
    ("Löthelfer", "Helping-hands stand"),
    ("Schrumpfschläuche", "Heat-shrink tubing"),
    ("Schleifpapier", "Sandpaper"),
    ("Schleifbock", "Bench grinder"),
    ("Feilenset", "File set"),
    ("Einmelzhilfen", "Heat-set inserts"),
    ("Imfrarotthermometer, Bosch", "Bosch infrared thermometer"),
    ("Akkuschrauber – Bosch", "Bosch cordless drill"),
    ("Bohrerset – Bosch, 103 Teile", "Bosch drill-bit set, 103 pieces"),
    ("Gewindeschneidesatz – 32 Kombonenten", "Tap-and-die set, 32 pieces"),
    ("Abisolierzange", "Wire stripper"),
    ("Digitaler-Messschieber", "Digital caliper"),
    ("Crimpzange", "Crimping pliers"),
    ("Schleifspitzen", "Grinding bits"),
    ("Drahtbürstenaufsatzset", "Wire-brush attachment set"),
    ("Lochblende für das C14", "Aperture stop for C14"),
    ("Stiftleis 2x3", "Pin header 2×3"),
    ("Stiftleis", "Pin headers"),
    ("Wiederstände – verschiedene – im Glas", "Assorted resistors in a jar"),
    ("Kondensatoren – viele – unterschiedliche", "Assorted capacitors (many)"),
    ("Regensensor", "Rain sensor"),
    ("Vakuumsklebeband – Rest", "Vacuum tape (remainder)"),
    ("Feinstaubsensor", "Particulate-matter sensor"),
    ("Kabelschuhe-Set", "Cable-lug set"),
    ("Spannungswandler/DC-DC Step Down Converter", "DC-DC step-down converter"),
    ("Schrittmotor", "Stepper motor"),
    ("Schrittmotorkontrollboards", "Stepper-motor driver boards"),
    ("Riemen-Set", "Belt set"),
    ("Montage Kleber, weiß, 370g", "White assembly adhesive, 370 g"),
    ("Schaniere", "Hinges"),
    ("Schnellwechselplatte", "Quick-release plate"),
    ("Mini Wasserwage", "Mini spirit level"),
    ("Riemen und Riemenscheiben, Set", "Belt and pulley set"),
    ("Kugellager", "Ball bearings"),
    ("Alumniumprofile", "Aluminium profiles"),
    ("Stepper motor Steuerungspaltine, King Print TMC2208 V3.0", "TMC2208 V3.0 stepper-motor driver boards"),
    ("Polyester Schnur", "Polyester cord"),
    ("Seilspanner", "Line tensioners"),
    ("Antennenkabel", "Antenna cable"),
    ("Aircell 5 Koabialkabel", "Aircell 5 coaxial cable"),
    ("T-Stück, 2xUHF-Buchse", "T-piece, 2× UHF socket"),
    ("Steckhülse M48 to 2’’, Omegon", "Omegon M48 to 2\" nosepiece"),
    ("Wegkorrektor für 1.25’’ Bino Ansätze 1.6x", "1.25\" binocular glass-path corrector 1.6×"),
    ("1.25’’ Verlängerungshülse 30mm, Omegon", "Omegon 1.25\" extension tube 30 mm"),
    ("Okularauszug Helical, 1.25’’, ZWO", "ZWO 1.25\" helical focuser"),
    ("Shelyak Optisches Set für Star’Ex HR", "Shelyak optical set for Star'Ex HR"),
    ("Wecker", "Alarm clock"),
    ("Alustuhl", "Aluminium chair"),
    ("Bürozeugs", "Office supplies"),
    ("große Trittleiter", "Large step ladder"),
    ("Trittleiter", "Step ladder"),
    ("großer Sack", "Large sack"),
    ("Einlegeböden Schreibtische (Metallplatte)", "Desk shelves (metal plate)"),
    ("orange und schwarzes Leerrohr", "Orange and black conduit"),
    ("Plane blau", "Blue tarpaulin"),
    ("Plane schwarz", "Black tarpaulin"),
    ("Plane trans", "Transparent tarpaulin"),
    ("Sonnenhut", "Sun hat"),
    ("Handwagen (blau-grau)", "Hand truck (blue-grey)"),
    ("Seile", "Ropes"),
    ("Tisch für die Säule, auf der die GM4000 QCI steht", "Table for the GM4000 QCI pier"),
    ("Abdunklungsfolie (Rolle)", "Blackout foil (roll)"),
    ("Abdunklungsfolie - blickdicht (Rolle)", "Opaque blackout foil (roll)"),
    ("Luftposterfolie – Rolle", "Bubble-wrap film (roll)"),
    ("Wagenheber (rot)", "Jack (red)"),
    ("Hebevorrichtung Montierung GM4000", "GM4000 mount lifting gear"),
    ("Verpackungsmaterial", "Packing material"),
    ("Trockenkartusche für die QHY-Kameras", "Desiccant cartridge for QHY cameras"),
    ("Trockenkartusche für die SBIG-Kameras", "Desiccant cartridge for SBIG cameras"),
    ("Arbeitshandschuhe – leicht", "Light work gloves"),
    ("Karabiner", "Carabiners"),
    ("Kleiner Campingtisch – Aluminium", "Small aluminium camping table"),
    ("Sonnensegel + 2x Spannschloss 8mm + 1x Karabiner", "Sun sail with two 8 mm turnbuckles and one carabiner"),
    ("Small steal balls", "Small steel balls"),
    ("Selbstschließender Kabelschlauch, ~5m", "Self-closing cable sleeve, ~5 m"),
    ("Schrühkleber", "Adhesive"),
    ("Pingzetten", "Tweezers"),
    ("Talkum", "Talc"),
    ("Locher", "Hole punch"),
    ("Canon 18-55mm Objektiv", "Canon 18–55 mm lens"),
    ("Canon 40mm Objektiv", "Canon 40 mm lens"),
    ("1.25''-Steckverlängerung für die ZWO ASI174MM Mini", "1.25\" extension for ZWO ASI174MM Mini"),
    ("QHYCFW3L – Zubehör", "QHYCFW3L accessories"),
    ("QHYCFW3XL – Zubehör", "QHYCFW3XL accessories"),
    ("ZWO EAF - Zubehör", "ZWO EAF accessories"),
    ("Handbücher EOS 700-D", "EOS 700D manuals"),
    ("Kiste mit vielen weiteren Manuals", "Box with additional manuals"),
    ("Sticks mit Mauals", "USB sticks with manuals"),
    ("Altes analoges Logbuch", "Old analogue logbook"),
    ("Bosch Infrarotthermometer", "Bosch infrared thermometer"),
    ("BME280 Sensor (Druck, Temperatur, Luftfeuchtigkeit)", "BME280 pressure/temperature/humidity sensor"),
    ("Netzwerkkabel (weiß, Länge unbekannt)", "Network cable (white, unknown length)"),
    ("Crimpzange (Baurix) + Aderendhülsen", "Crimping pliers (Baurix) with ferrules"),
    ("Tasche Toughbook", "Toughbook bag"),
    ("BACHES Koffer", "BACHES case"),
    ("DADOS Koffer II", "DADOS case II"),
    ("DADOS Koffer", "DADOS case"),
    ("RCU Koffer", "RCU case"),
    ("ST-7/8 Koffer", "ST-7/8 case"),
    ("STF 8300M Koffer", "STF-8300M case"),
    ("RCA-Stecker auf 5.5x2.1mm-Buchse", "RCA plug to 5.5x2.1 mm socket"),
    ("serielles COM-Port-Kabel (Cross-Over????, 2x Stecker, 0xBuchse)", "Serial COM cable (possibly crossover; two plugs, no socket)"),
    ("Tuben der Schmidt Cassegrain Szsteme", "Schmidt-Cassegrain OTA manuals"),
    ("Correction for the STIS Echell Blaze Function", "Correction for the STIS echelle blaze function"),
    ("BACHES Standardkalibrationseinheit Netzteil", "BACHES standard calibration-unit power supply"),
    ("BACHES Standardkalibrationseinheit", "BACHES standard calibration unit"),
    ("BACHES Kalibrationslampe", "BACHES calibration lamp"),
    ("DADOS Kalibrationslampe", "DADOS calibration lamp"),
    ("BACHES Echelle-Spektrograph", "BACHES echelle spectrograph"),
    ("DADOS Spektrograph", "DADOS spectrograph"),
    ("Teleskop OST (CDK20)", "OST telescope (CDK20)"),
    ("TS-Optics Starscope 80/600 mm Refraktor", "TS-Optics Starscope 80/600 mm refractor"),
    ("TS-Optics PHOTOLINE 130 mm f/7 EDT Triplet Apo - 3,7\" Auszug", "TS-Optics PHOTOLINE 130 mm f/7 EDT triplet apo"),
    ("Metallic dew cap for the RASA", "Metallic dew cap for the RASA"),
    ("separate EQ clmap to mount onto Stronghold Tangent", "Separate EQ clamp for Stronghold Tangent"),
    ("Dew Heater Ring, 11‘‘, Celestron – Zubehör + alter Konterring der Schmidtplatte des RASA", "Celestron 11\" dew-heater ring accessories"),
    ("Heitzmanschette", "heater sleeve"),
    ("Direktes Verbindungskabel EQ8 → USB, Pierro", "Direct EQ8-to-USB cable, Pierro"),
    ("Tubusklappe mit Flatfield für 130mm APO, WandereCover V4-EC 150mm", "WandererCover V4-EC 150 mm tube cover with flat field for 130 mm APO"),
    ("Stahlzapfen Berlebacj tripods", "Steel pins for Berlebach tripods"),
    ("STF-8300M Werkzeug", "STF-8300M tools"),
    ("Besen", "Broom"),
    ("Messer", "Knife"),
    ("Lineal", "Ruler"),
    ("Hammer", "Hammer"),
    ("Relai doppelt", "Double relay"),
    ("Lüfter", "Fan"),
    ("Antenne Arduino – gebraucht – reparriert (defekt)", "Arduino antenna — used, repaired (defective)"),
    ("Antenne Arduino", "Arduino antenna"),
    ("Kabel - unterschiedlicher Länge und Steckertypen", "Cables of various lengths and connectors"),
    ("Diverse Kabel – viele – in Tüte", "Assorted cables (many) in a bag"),
    ("Solarpanel – klein", "Small solar panel"),
    ("Flachbandkabel", "Ribbon cable"),
    ("Halbrundkopfschrauben", "Button-head screws"),
    ("Zylinderschrauben", "Socket-head cap screws"),
    ("HF Balun", "HF balun"),
    ("SMA-Koaxialadapter", "SMA coaxial adapter"),
    ("Computer a12", "Computer a12"),
    ("Computer a13", "Computer a13"),
    ("Computer Columba", "Computer Columba"),
    ("Computer Polaris", "Computer Polaris"),
    ("Raspberri Pi", "Raspberry Pi"),
    ("Hailege Nano", "Hilege Nano"),
    ("10xDC Verbinder Set", "DC connector set (10 pcs)"),
    ("Set: Dupont Connectors and Crimp Pins", "Dupont connector and crimp-pin set"),
    ("Set: T-XH Connector Kit", "T-XH connector kit"),
    ("PCB-Lochplatten-Set mit Stecker", "Perfboard set with connectors"),
    ("UNO R3 Proto Shield Prototyp Expansion Board mit SYB-170 Mini Breadboar", "UNO R3 proto shield with SYB-170 mini breadboard"),
    ("I2C Multiplexer Breakout Board 1.8 V - 5 V 8 Kanal – TCA9548A, mostly defect?", "TCA9548A 8-channel I2C multiplexer breakout"),
    ("DC Einstellbarer Buck-Boost-Wandler Spannungsregler DC6-36V 120W", "Adjustable DC 6–36 V 120 W buck-boost converter"),
    ("3,3 V DC-DC Step Down Stromversorgungsmodul, AMS1117", "AMS1117 3.3 V DC-DC step-down module"),
    ("ARCELI Buck Boost Converter Anzeige", "ARCELI buck-boost converter with display"),
    ("Heemol ESP32 S3 N16R8 DevKitC-1 Module, ESP32 S3, WiFi, Bluetooth 5.0, USB C, anschließbare 2.4G Antenne", "ESP32-S3 N16R8 DevKitC-1 (Wi-Fi, Bluetooth 5.0, USB-C, 2.4 GHz antenna)"),
    ("M2, M3, M4, M5, M6 female threads – zum einschmelzen", "M2–M6 heat-set threaded inserts"),
    ("USB-B-Ports", "USB-B ports"),
    ("Raspberry Pi Camera Module 3, NoIR, Wide", "Raspberry Pi Camera Module 3 NoIR Wide"),
    ("Raspberry Pi Camera Module 3, NoIR", "Raspberry Pi Camera Module 3 NoIR"),
    ("Pi5 display cable", "Pi 5 display cable"),
    ("DC connector – male, with cable", "DC connector, male, with cable"),
    ("DC connector – female, with cable", "DC connector, female, with cable"),
    ("DC connectors – female & male – diverse – many, with cable", "Assorted DC connectors, male and female, with cable"),
    ("Breadboards, verschiedene Größen", "Breadboards, various sizes"),
    ("Breakout board antenna", "Antenna breakout board"),
    ("Rain sensor board red – without sensor", "Red rain-sensor board without sensor"),
    ("Stemma QT Kabel-Kit", "STEMMA QT cable kit"),
    ("Resitor kit – BOJACK – 17 values – 1/4W +/-1% - ~630 pieces", "BOJACK resistor kit, 17 values, 1/4 W ±1%, ~630 pcs"),
    ("LM2596, DC-DC Buck Converter Voltage Regulator Power Supply Module, 3.0-40 V to 1.5-35 V Power Supply Step Down Module", "LM2596 DC-DC buck converter 3.0–40 V to 1.5–35 V"),
    ("Arduino Nano head/adapter", "Arduino Nano header/adapter"),
    ("Coper wire spool,6 colors,UL1007", "Copper wire spool, 6 colours, UL1007"),
    ("UV Analog Sensor", "UV analogue sensor"),
    ("UV Index Sensor 240-370nm, Gravity", "Gravity UV-index sensor 240–370 nm"),
    ("Display for Raspberry Pi", "Raspberry Pi display"),
    ("ESP32 Mini, USB C, WiFi, Bluetooth", "ESP32 Mini, USB-C, Wi-Fi, Bluetooth"),
    ("ESP32, USB C, WiFi, Bluetooth", "ESP32, USB-C, Wi-Fi, Bluetooth"),
    ("SAMYANG,-Objektiv F2.0/135mm ED UMC for Canon", "Samyang 135 mm f/2.0 ED UMC lens for Canon"),
    ("Canon EF Lense to T2 mount", "Canon EF to T2 adapter"),
    ("USB 5V Power Adapter", "USB 5 V power adapter"),
    ("WATER-STOP, Abdichtungsmasse, 1kg", "WATER-STOP sealant, 1 kg"),
    ("Lines - Guiding camera: OA64, d=51mm, f=182mm", "Guiding-camera lens OA64, d=51 mm, f=182 mm"),
    ("Kamera, IMX290-83 IR-CUT", "IMX290-83 IR-cut camera"),
    ("GPS sensor NEO6MV2", "NEO-6MV2 GPS sensor"),
    ("LCD Extension board for Arduino", "Arduino LCD extension board"),
    ("Stepper motor, RoHS", "Stepper motor, RoHS"),
    ("SDRplay RSP1B + USB-Kabel", "SDRplay RSP1B with USB cable"),
    ("Filter ND8(0.9) 3 Stops, 67mm, HOYA", "Hoya ND8 (0.9) 3-stop filter, 67 mm"),
    ("Filter ND16(1.2) 4 Stops, 67mm, HOYA", "Hoya ND16 (1.2) 4-stop filter, 67 mm"),
    ("Filter ND32(1.5) 5 Stops, 67mm, HOYA", "Hoya ND32 (1.5) 5-stop filter, 67 mm"),
    ("Acer H6830BD DLP Projector (4K UHD (3,840 x 2,160 Pixels) 4,000 ANSI Lumens, 10,000:1 Contras", "Acer H6830BD 4K DLP projector"),
    ("Handheld Thermography Camera, HIKMICRO, Model B01 + USB charger and cable", "HIKMICRO B01 handheld thermography camera"),
    ("Meta Quest 3 VR Headset + Case * Elite Strap", "Meta Quest 3 VR headset with case and Elite Strap"),
    ("Video Capture Card, 4K HDMI auf USB C/A Capture Card", "4K HDMI to USB-C/A video capture card"),
    ("Kabel mit Kabelschuhen (U förmig) und Buchse mit 2 Pinaufnahmen für und mit verschiedenen Adapter zur Stromversorgung (wie Netzteil)", "Power cable with U-lugs and 2-pin socket, plus adapters"),
    ("Kabel GM4000 HPS (Netzwerkkabel, Stromkalbel, Remotekabel)", "GM4000 HPS cable set (network, power, remote)"),
    ("Kabel eine Seite mit Klinkenstecker", "Cable with jack plug on one end"),
    ("unterschiedliche Stromkabel (mit und ohne Stecker)", "Assorted power cables, with and without plugs"),
    ("Kabel für „Outdoor Telescope Power“", "Outdoor Telescope Power cable"),
    ("Kabel für das Netzteil (Baader, gelb) der GM4000 (mit integriertem Steuerungskabel)", "Yellow Baader PSU cable for GM4000 with integrated control cable"),
    ("Verbindungskabel – Strom – 2,1mm x 5,5mm Stecker – Stecker auf Stecker", "DC power cable 2.1×5.5 mm, plug to plug"),
    ("Y-Kabel – Strom – 2,1mm x 5,5mm Stecker – 1 auf 2", "DC Y-cable 2.1×5.5 mm, 1-to-2"),
    ("Y-Kabel – Strom – 2,1mm x 5,5mm Stecker – 1 auf 4", "DC Y-cable 2.1×5.5 mm, 1-to-4"),
    ("Stromkabelverlängerung für die Kameras", "Camera power-cable extension"),
    ("Kabel für die Stromversorgung der EQ8", "EQ8 power cable"),
    ("Kabel USB to DC 5.5x2.1mm", "USB to DC 5.5×2.1 mm cable"),
    ("Stromkabel-Set (blau, schwarz, grau, gelb-grün)", "Power-cable set (blue, black, grey, yellow-green)"),
    ("USB3-Verlängerungskabel", "USB 3 extension cable"),
    ("USB-A 3.0 Verlängerungskabel", "USB-A 3.0 extension cable"),
    ("ZWO USB2.0 Cabel A-C", "ZWO USB 2.0 cable A–C"),
    ("USB-2.0-Verlängerungskabel", "USB 2.0 extension cable"),
    ("USB-A zu USB-mini Adapterkabel", "USB-A to USB-mini adapter cable"),
    ("kurzes schwarzes Netzwerkkabel", "Short black network cable"),
    ("Aktives USB2-Kabel", "Active USB 2 cable"),
    ("USB-Kabel: A → B", "USB cable A–B"),
    ("Netzkabel STF8300", "STF-8300 mains cable"),
    ("Guider ST4-Kabel (grau, wahrscheinlich RJ11-Stecker)", "ST4 guider cable (grey, likely RJ11)"),
    ("Guider ZWO ST4-Kabel (schwarz, 2m)", "ZWO ST4 guider cable (black, 2 m)"),
    ("RCU Steuerungskabel", "RCU control cable"),
    ("M68-Adapterset", "M68 adapter set"),
    ("M68-Deckel mit Innnengewinde (TS-OPtics, KIM68)", "TS-Optics KIM68 M68 cap with internal thread"),
    ("100mm M68-Adapter aus dem M68-Adapterset", "100 mm M68 adapter from the M68 adapter set"),
    ("10mm M68-Adapter - M68 Extension tube 10mm", "M68 extension tube 10 mm"),
    ("Kabel für die CGE-Pro", "CGE-Pro cable"),
    ("Schrauben für die CGX-L", "CGX-L screws"),
    ("Schrauben für die CGE-Pro", "CGE-Pro screws"),
    ("Kabel für die Advanced GT", "Advanced GT cable"),
    ("Winkelstecker (Quick-Disconnect Elbowed Plug)", "Quick-disconnect elbowed plug"),
    ("Pulleys for strain relief", "Strain-relief pulleys"),
    ("8xAA Battery Pack for RASA fans", "8× AA battery pack for RASA fans"),
    ("Omegon Pro Powerbank 96000", "Omegon Pro power bank 96000"),
    ("Celestron SkyPortal WiFi Adapter", "Celestron SkyPortal Wi-Fi adapter"),
    ("Celestron Focus Motor", "Celestron focus motor"),
    ("StarSence Sky-Watcher Retrofit Kit", "StarSense Sky-Watcher retrofit kit"),
    ("StarSence Autoalign Modul", "StarSense AutoAlign module"),
    ("ZWO Kamera", "ZWO camera"),
    ("Webcam Philips", "Philips webcam"),
    ("Dell Tastatur", "Dell keyboard"),
    ("Dell Maus", "Dell mouse"),
    ("Logitech Maus", "Logitech mouse"),
    ("IP-Telefon, CISCO, 7940 series", "Cisco 7940 IP phone"),
    ("TP-Link Outdoorrouter", "TP-Link outdoor router"),
    ("Portable SSD Samsung T5", "Samsung T5 portable SSD"),
    ("Portable Samsung SSD – 1TB", "Samsung 1 TB portable SSD"),
    ("Portable Samsung SSD – 2TB, T7", "Samsung T7 2 TB portable SSD"),
    ("128GB SD-Karte – SanDisk Ultra", "SanDisk Ultra 128 GB SD card"),
    ("4GB USB-Stick", "4 GB USB stick"),
    ("USB-3.0-7-Port-Hub tp-link", "TP-Link 7-port USB 3.0 hub"),
    ("Serial to USB-2 converter", "Serial to USB 2 converter"),
    ("Adapter USB-A auf LAN", "USB-A to LAN adapter"),
    ("Adapter LAN auf USB-A", "LAN to USB-A adapter"),
    ("Adapter USB-A auf Maus", "USB-A to mouse adapter"),
    ("Adapter USB-A to DC 5.5x2.1mm", "USB-A to DC 5.5×2.1 mm adapter"),
    ("Adapter DC 5.5x2.1mm to USB-A", "DC 5.5×2.1 mm to USB-A adapter"),
    ("2.5’’ Adapter Dell Festplattenrahmen", "Dell 2.5\" drive caddy"),
    ("Raspberry Pi 5 Active Cooler", "Raspberry Pi 5 Active Cooler"),
    ("Raspberry Pi 4B/3B+3B/2/B+ Active Cooler, verbaut", "Raspberry Pi 4/3/2 Active Cooler"),
    ("Raspberry Pi 4B/3B+3B/2/B+ Active Cooler", "Raspberry Pi 4/3/2 Active Cooler"),
    ("Raspberry Pi 4B passive cooler", "Raspberry Pi 4B passive cooler"),
    ("PCIe to M.2 NVMe Shield | Raspberry Pi 5", "Raspberry Pi 5 PCIe to M.2 NVMe shield"),
    ("NVMe 250GB SSD (PNY)", "PNY 250 GB NVMe SSD"),
    ("Raspberry Pi 4 B – 4GB", "Raspberry Pi 4 B 4 GB"),
    ("Raspberri Pi 5 – 8GB", "Raspberry Pi 5 8 GB"),
    ("Raspberri Pi 5 – 16GB", "Raspberry Pi 5 16 GB"),
    ("AAA 1,5 V Batterien", "AAA 1.5 V batteries"),
    ("AA 1.5V", "AA 1.5 V batteries"),
    ("E 9V", "9 V batteries"),
    ("Grundierung – Primer – Spray – edding", "Edding primer spray"),
    ("TS Optics Antireflexfarbe", "TS-Optics anti-reflection paint"),
    ("Siliconentferner", "Silicone remover"),
    ("NIGRIN – Langzeit-Rostschutz", "NIGRIN long-term rust protection"),
    ("NIGRIN – Rost-Stop", "NIGRIN rust stop"),
    ("NIGRIN – Klarlack-Spray", "NIGRIN clear-coat spray"),
    ("Matt White, MASTON, Spray Color, almost empty", "Maston matt white spray, almost empty"),
    ("ABS filament – white", "ABS filament, white"),
    ("ABS+ filament – black", "ABS+ filament, black"),
    ("PLA fillament – white", "PLA filament, white"),
    ("PLA filament – black", "PLA filament, black"),
    ("ePLA-CF filament – black", "ePLA-CF filament, black"),
    ("PETG filament - white", "PETG filament, white"),
    ("PETG filament – black", "PETG filament, black"),
    ("PETG, weiß, 1kg", "PETG filament, white, 1 kg"),
    ("ASA – black", "ASA filament, black"),
    ("ASA – white", "ASA filament, white"),
    ("Metall-(Messing)-Folie MS63, 150x2500x0,025mm", "MS63 brass foil 150×2500×0.025 mm"),
    ("Metallfolie (Messing MS 63, 150x2500mm)", "MS63 brass foil 150×2500 mm"),
    ("Fine line tape, blue, different width", "Blue fine-line tape, various widths"),
    ("Tesa – Standard Malerkrep", "Tesa standard painter's tape"),
    ("Pompons (100 Stück)", "Pom-poms (100 pcs)"),
    ("Pinsel", "Brushes"),
    ("BACHES accessories", "BACHES accessories"),
    ("Sky-Watcher EVOGUIDE 50ED – Teile", "Sky-Watcher EVOGUIDE 50ED parts"),
    ("Sky-Watcher EVOGUIDE 50ED, Teile", "Sky-Watcher EVOGUIDE 50ED parts"),
    ("50mm Finders Scope", "50 mm finderscope"),
    ("M68 Adapter for CDK 14 - 1000 same as for Planewave 0.66 Reducer incl. Screws (1323840)", "M68 adapter for CDK 14–1000 / PlaneWave 0.66 reducer, with screws"),
    ("Baader UFC Filter Slider 50x50", "Baader UFC 50×50 mm filter slider"),
    ("Classic Ortho 1.25’’, 10mm", "Classic Ortho 1.25\", 10 mm"),
    ("Classic Ortho 1.25’’, 18mm", "Classic Ortho 1.25\", 18 mm"),
    ("Lunt Solar System – Zoom Okular 7,2mm -21,5mm", "Lunt solar zoom eyepiece 7.2–21.5 mm"),
    ("15mm WideView 1 ¼ “", "15 mm WideView 1.25\""),
    ("25mm Ploessl 1 ¼ “", "25 mm Plössl 1.25\""),
    ("32mm Ploessl 1 ¼ “", "32 mm Plössl 1.25\""),
    ("40mm Ploessl 1 ¼ “", "40 mm Plössl 1.25\""),
    ("6mm Ploessl 1 ¼ “", "6 mm Plössl 1.25\""),
    ("9mm Ploessl 1 ¼ “", "9 mm Plössl 1.25\""),
    ("StarDiagonal 1 ¼ “", "Star diagonal 1.25\""),
    ("Mark V Großfeld-Binokular", "Mark V giant binocular viewer"),
    ("Hyperion 13mm 68 Grad", "Hyperion 13 mm 68°"),
    ("Hyperion 21mm 68 Grad", "Hyperion 21 mm 68°"),
    ("Hyperion 36mm 72 Grad", "Hyperion 36 mm 72°"),
    ("Mark IV Zoom (mit Anbauten: M34/T2-Adapter, T-2 Quick Changer, ...)", "Mark IV zoom eyepiece with M34/T2 adapter and T-2 quick changer"),
    ("Glaswegkorrektor Bino Ansätze", "Binocular glass-path corrector"),
    ("1,7-mm-Fisheye-Objektiv, M12*0,5, f1,7mm, 1/2,5-Zoll-Format. Etwa 180 Grad Weitwinke", "1.7 mm fisheye lens, M12×0.5, 1/2.5\" format, ~180°"),
    ("Baader Spectroscopy Barlow", "Baader spectroscopy Barlow"),
    ("Hyperion Zoom Barlow Linse 2.25x", "Hyperion zoom Barlow 2.25×"),
    ("Astro Physics \"Advanced\" Convertible Barlow Lens – Adapter", "Astro-Physics Advanced Convertible Barlow — adapter"),
    ("Astro Physics \"Advanced\" Convertible Barlow Lens, BARADV", "Astro-Physics Advanced Convertible Barlow BARADV"),
    ("Barlow Linse 2x, 1 ¼ ”", "2× Barlow, 1.25\""),
    ("1,7x glass path Corrector", "1.7× glass-path corrector"),
    ("Focussing Eyepiece Holder 1 ¼ ”", "Focusing eyepiece holder 1.25\""),
    ("Adapter: Canon lens mount to 1 ¼ ”", "Canon lens mount to 1.25\" adapter"),
    ("Baader Protective T-Ring (Adapter: Canon lens mount to 2”)", "Baader protective T-ring, Canon to 2\""),
    ("1.25’ camera adapter (ZWO)", "ZWO 1.25\" camera adapter"),
    ("Adapter 2” - 1 ¼”", "2\" to 1.25\" adapter"),
    ("Adapter T2 - 1 ¼”, nose piece", "T2 to 1.25\" nosepiece"),
    ("Adapter 2”-8.3cm; Adapter von C8 und C11 auf 2\"-Okularklemme", "2\" to 8.3 cm adapter (C8/C11 to 2\" eyepiece clamp)"),
    ("Adapter Webcam auf 1 ¼“", "Webcam to 1.25\" adapter"),
    ("FR-4 Focusing Ring Collar 1 ¼“ (Stop Ring)", "FR-4 focusing ring collar 1.25\" (stop ring)"),
    ("Hyperion Finetuning Ring 14mm", "Hyperion fine-tuning ring 14 mm"),
    ("S52 Nosepiece (T-2-Steckhülse)", "S52 T-2 nosepiece"),
    ("Celestron Star Diagonal 1 ¼ “", "Celestron 1.25\" star diagonal"),
    ("Umlenkspiegel 90 Grad, 2\" (gross) mit Okularklemme", "2\" 90° star diagonal with eyepiece clamp"),
    ("Umlenkspiegel 90 Grad, 2\" (gross)", "2\" 90° star diagonal"),
    ("Umlenkprisma 90 Grad, 1 ¼” (klein)", "Small 1.25\" 90° star diagonal (prism)"),
    ("2\" Nose Piece with safety kerf #19A", "2\" nosepiece with safety kerf #19A"),
    ("2\" T-2 Nosepiece for CCD & DSLR Cameras", "2\" T-2 nosepiece for CCD and DSLR cameras"),
    ("2”/T-2 Nosepiece", "2\"/T-2 nosepiece"),
    ("MARK IV Okular (Adapter)", "Mark IV eyepiece adapter"),
    ("Teleskopschiene (Schwalbenschwanz, zur Montierung auf der Celestron Advanced GT)", "Dovetail bar for Celestron Advanced GT"),
    ("Celestron Dovetail Bar – 11’’", "Celestron 11\" dovetail bar"),
    ("TS-Optics XL Premium Losmandy Level Prismenklemme", "TS-Optics XL Premium Losmandy-level saddle clamp"),
    ("Commetfilter, C2 Swan-Band filter, Baader, 2’’", "Baader C2 Swan-band comet filter, 2\""),
    ("Calcium GEN-II 1.25“", "Calcium GEN-II filter 1.25\""),
    ("Clear filter 2”", "Clear filter 2\""),
    ("Semi-APO filter, 1.25”", "Semi-APO filter 1.25\""),
    ("Semi-APO filter, 2”", "Semi-APO filter 2\""),
    ("Halpha 6nm CCD 1 ¼ “", "H-alpha 6 nm CCD filter 1.25\""),
    ("OIII CCD 1 ¼ “", "OIII CCD filter 1.25\""),
    ("UV/IR Cut filter, 1.25’’", "UV/IR cut filter 1.25\""),
    ("H-Beta Narrowband 8,5nm CCD, 1.25’’", "H-beta 8.5 nm CCD narrowband filter 1.25\""),
    ("S II Narrowband CCD, 1.25’’", "SII CCD narrowband filter 1.25\""),
    ("Solar Continuum 10 nm, 1.25’’", "Solar Continuum 10 nm, 1.25\""),
    ("Solar Continuum 7,5 nm, 1.25’’", "Solar Continuum 7.5 nm, 1.25\""),
    ("Solar Continuum 7,5 nm, 2’’", "Solar Continuum 7.5 nm, 2\""),
    ("UHC-S L-Booster, 1.25’’", "UHC-S L-Booster 1.25\""),
    ("IR Pass Filter 685nm, 2’’", "IR-pass filter 685 nm, 2\""),
    ("Moon & Skyglow-Filter, 2’’", "Moon & Skyglow filter 2\""),
    ("UHC-S Nebula Filter, 2’’", "UHC-S nebula filter 2\""),
    ("Baader Single Polarising-Filter 2“", "Baader single polarising filter 2\""),
    ("Baader SLOAN Photometric filter set 50x50mm, u', y', z-s', g', r', i'", "Baader SLOAN photometric filter set 50×50 mm"),
    ("Baader SLOAN Photometric filter set 50,4mm rund, u', y', z-s', g', r', I'", "Baader SLOAN photometric filter set 50.4 mm round"),
    ("Baader 3.5/4nm f/2 Ultra-Highspeed Filter set 50x50mm - CMOS-optimized, Halpha, OIII, SII", "Baader 3.5/4 nm f/2 ultra-highspeed Ha/OIII/SII set 50×50 mm"),
    ("ND-Filter für die Aurora-Flatfieldfolie", "ND filter for the Aurora flat-field panel"),
    ("IR850 Filter, QHYCCD", "QHYCCD IR850 filter"),
    ("890mm CH4 Filter, QHYCCD", "QHYCCD 890 nm CH4 filter"),
    ("IR/CUT Filter, QHYCCD", "QHYCCD IR-cut filter"),
    ("BAADER RGB-C Clear Focusing 36mm Filter", "Baader RGB-C clear focusing filter 36 mm"),
    ("BAADER SII Narrowband 8nm 36mm CCD Filter", "Baader SII 8 nm CCD filter 36 mm"),
    ("Sonnenfilter - alt (Astromann)", "Astromann solar filter (old)"),
    ("Sonnenfilter - neu, 295-315mm (Astromann)", "Astromann solar filter, 295–315 mm (new)"),
    ("Sonnenfilter - alt; 220-240mm (Astromann)", "Astromann solar filter, 220–240 mm (old)"),
    ("Sonnenfilter - ganz alt", "Solar filter (very old)"),
    ("Sonnenfilter - neu; ASTF 2000", "ASTF 2000 solar filter (new)"),
    ("Sonnenfilter; ASTF 140", "ASTF 140 solar filter"),
    ("Alpy calibration module (PF0037, S/N: 7L -351) - Calibration unit for DADOS", "Alpy calibration module for DADOS (PF0037, S/N 7L-351)"),
    ("Remote Unit for the Alpy calibration module (DIY)", "DIY remote unit for the Alpy calibration module"),
    ("Stativ Advanced GT", "Advanced GT tripod"),
    ("Stativ CGX-L", "CGX-L tripod"),
    ("Stativ CGE-Pro", "CGE-Pro tripod"),
    ("Berlebach Planet mit Adapter für CGX-L", "Berlebach Planet with CGX-L adapter"),
    ("Celestron SkyScout", "Celestron SkyScout"),
    ("Skywatcher Heliostar 76/630 Halpha", "Sky-Watcher Heliostar 76/630 H-alpha"),
    ("Serial GNSS Receiver MD6 u-blox 6, 1.5m", "MD6 u-blox 6 serial GNSS receiver, 1.5 m"),
    ("PegasusAstro Pocket Powerbox Advance (PPBADV), Stromversorgung", "PegasusAstro Pocket Powerbox Advance (PPBADV)"),
    ("CGE-Pro Elektronikbox", "CGE-Pro electronics box"),
    ("ZWO EAF (electronic automatic focuser) – mounted to the APO", "ZWO EAF electronic focuser"),
    ("Losmandy Dovetail for C14 – mounted to C14", "Losmandy dovetail for C14"),
    ("Losmandy Dovetail – 355mm - Radioschüssel", "Losmandy dovetail 355 mm — radio dish"),
    ("Geoptik Losmandy Dovetail C8", "Geoptik Losmandy dovetail for C8"),
    ("Vixen EQ5 Dovetail – 220mm – black", "Vixen EQ5 dovetail 220 mm, black"),
    ("Vixen EQ5 Dovetail – 335mm – red", "Vixen EQ5 dovetail 335 mm, red"),
    ("Artesky Guidescope MKII 60mm", "Artesky guidescope MKII 60 mm"),
    ("Dew Heater Strip, 560mm, SVBONY, Heitzmanschette", "SVBONY dew-heater strip 560 mm"),
    ("Dew Heater Strip, 480mm, SVBONY, Heitzmanschette", "SVBONY dew-heater strip 480 mm"),
    ("Dew Heater Strip, 215mm, Lacerta, Heitzmanschette", "Lacerta dew-heater strip 215 mm"),
    ("Dew Heater Ring, 11‘‘, Celestron", "Celestron 11\" dew-heater ring"),
    ("Stronghold Tangent Assembly - blue color", "Stronghold tangent assembly, blue"),
    ("Stronghold Tangent Assembly – black color", "Stronghold tangent assembly, black"),
    ("Mounting block for leveling counterweight bar M14 D16 for CDK’s", "Leveling counterweight-bar mounting block M14 D16 for CDKs"),
    ("QHY5III462C (+ adapter and filter)", "QHY5III462C with adapter and filter"),
    ("GPS-Module APKLVSR, GPS6MV2, Batch number: XM-2024-8-15", "APKLVSR GPS6MV2 module"),
    ("GPS-Module Aideepen 2 ADET – defekt", "Aideepen GPS module — defective"),
    ("GPS-Module Aideepen 2 ADET", "Aideepen GPS module"),
    ("Arduino Typ: ?", "Arduino (unidentified type)"),
    ("Arduino Leonardo (defekt)", "Arduino Leonardo — defective"),
    ("Arduino Uno R4 Wifi", "Arduino Uno R4 WiFi"),
    ("Arduino Nano Clone – Nano V3.0 ATmega328, CH340G, Paradisetronic.com and SHUNSHUN", "Arduino Nano clone V3.0 ATmega328 CH340G"),
    ("Kärcher K2 Power Control", "Kärcher K2 Power Control"),
    ("Gardena – Geräteadapter G ¾” – Durchmesser: 26,5mm", "Gardena device adapter G 3/4\", 26.5 mm"),
    ("Frosch Neutralreiniger", "Frosch all-purpose cleaner"),
    ("AutoHartWax (SONAX)", "SONAX hard car wax"),
    ("Rain X Regenabweiser", "Rain-X rain repellent"),
    ("Fix-Klar Regenabweiser", "Fix-Klar rain repellent"),
    ("Silicagel Orange (Trockenmittel, 150g)", "Orange silica gel, 150 g"),
    ("Silica Gel Orange (Desicant) - 1kg", "Orange silica gel, 1 kg"),
    ("Baader #2 Teflon-White, 10ml, -25 to 40 Grad C", "Baader #2 Teflon-White, 10 ml, −25 to 40 °C"),
    ("4 color torch", "Four-colour torch"),
    ("Black light torch", "Blacklight torch"),
    ("Laser pointer green", "Green laser pointer"),
    ("0.8mm Nylon cord coil (+100m left) with some ferrule", "0.8 mm nylon cord reel (~100 m left) with ferrules"),
    ("small cord coil (blue, white, orange) - synthetic fiber", "Small synthetic-fibre cord reels (blue, white, orange)"),
    ("Cord 60m", "Cord, 60 m"),
    ("Notebook tent - iCap MIDPRO", "iCap MIDPRO notebook tent"),
    ("Rubber mat", "Rubber mat"),
    ("Small bags", "Small bags"),
    ("Aluminium mesh 1x5m", "Aluminium mesh 1×5 m"),
    ("Weller WE 1010 Lötstation inkl. Lötkolbenhalter", "Weller WE 1010 soldering station with iron stand"),
    ("Endoskop VOLTCRAFT BS-26 + Zubehör", "Voltcraft BS-26 endoscope and accessories"),
    ("Multimeter VOLTCRAFT VC155", "Voltcraft VC155 multimeter"),
    ("TCF-S Focuser (OPTEC, Inc.)", "Optec TCF-S focuser"),
    ("Dispersion corrector", "Dispersion corrector"),
    ("Electronic collimator OCAL 4.0", "OCAL 4.0 electronic collimator"),
    ("Celestron CGX-L", "Celestron CGX-L"),
    ("Celestron CGE-Pro", "Celestron CGE-Pro"),
    ("Celestron Advanced GT", "Celestron Advanced GT"),
    ("Sky-Watcher EQ8-R", "Sky-Watcher EQ8-R"),
    ("Celestron C14", "Celestron C14"),
    ("Celestron C11", "Celestron C11"),
    ("Celestron C8", "Celestron C8"),
    ("Celestron RASA 11", "Celestron RASA 11"),
    ("Coronado Solar Max II", "Coronado SolarMax II"),
    ("Mini Solar System 3D prints", "Mini solar-system 3D prints"),
    ("Switch, LCS-883R-SW800M+", "LCS-883R-SW800M+ switch"),
    ("RC-7 Adapter", "RC-7 adapter"),
    ("Null Modem", "Null-modem adapter"),
    ("Outdoor Telescope Power (Baader, gelb); Input> 100-240V AC 8,2A, 50/60 Hz, Output: 27V 22.2 A 600 W", "Baader yellow Outdoor Telescope Power 27 V 22.2 A 600 W"),
    ("Baader OTP Outdoor Telescope Switching Power 12V/5A/60W with Quick-Disconnect (defekt)", "Baader OTP 12 V/5 A/60 W with quick-disconnect — defective"),
    ("Outdoor Telescope Power (Baader): Input: 12V, 3.3A, Output: 12V, 5A, 60W", "Baader Outdoor Telescope Power 12 V 5 A 60 W"),
    ("AC/DC Adapter, Output 16V & 2A, with socket adapter", "AC/DC adapter 16 V 2 A with socket adapter"),
    ("Netzteil (GlobTek) ST-7/8 Input: 100-240V, 1.3-0.6A, 60/50Hz, Output: 5V/5A, 12V/1.5A, 12V/0.5A", "GlobTek ST-7/8 power supply"),
    ("Verschiedene Netzteile für die Kameras: Input: 100-240V, 1A, 60/50Hz, Output: 12V, 2-6A", "Assorted camera power supplies, 12 V 2–6 A"),
    ("Netzteil YG-80W (Yuegang), Output: 12V, 6A", "Yuegang YG-80W power supply, 12 V 6 A"),
    ("Netzteil PSAC60M-120 (Phihong), Output: 12V, 5A", "Phihong PSAC60M-120 power supply, 12 V 5 A"),
    ("Netzteil SBIG (60013) – FSP GROUP INC.; Output: 12V, 3.33A", "SBIG FSP 60013 power supply, 12 V 3.33 A"),
    ("Netzteil für die Advanced-GT-Montierung", "Advanced GT mount power supply"),
    ("Netzteil für die Flatfieldfolie (50x50cm) für das CDK20 (EL Inverter)", "EL inverter for the 50×50 cm CDK20 flat-field panel"),
    ("Netzteil für die Flat Field Generator (Flatfieldfolie) für das C14 und kleiner", "Power supply for the C14 flat-field generator"),
    ("Netzteil AC/DC; Input: AC 110-240V 50/60Hz; Output DC 5V 1A", "AC/DC adapter 5 V 1 A"),
    ("Universal power supply - 5.25V3A - 8 Tips", "Universal power supply 5.25 V 3 A, 8 tips"),
    ("Power supply - 5V / 1A", "Power supply 5 V 1 A"),
    ("AC/DC Adapter", "AC/DC adapter"),
    ("Raspberry Pi 5 Netzteil – nicht original", "Raspberry Pi 5 power supply (third-party)"),
    ("USB 3.0 Cable A→B, 1.8m", "USB 3.0 cable A–B, 1.8 m"),
    ("CDs", "CDs"),
    ("Software Canon 700D (CDs)", "Canon 700D software (CDs)"),
    ("Celestron CGEPro (Deutsch und Englisch)", "Celestron CGE-Pro manual (German and English)"),
    ("Celestron C6, C8, C9.25, C11 (Deutsch und ENglisch)", "Celestron C6–C11 manual (German and English)"),
    ("Schmidt Cassegrain Optical Tube Assembly C6, C8, C9.25m, C11, C14", "Schmidt-Cassegrain OTA manual C6–C14"),
    ("Advanced & Advanced GoTo Montierung", "Advanced / Advanced GoTo mount manual"),
    ("Aurora FlatfieldLeuchtfolie", "Aurora flat-field panel manual"),
    ("Geoptik - Flat Field Generator", "Geoptik flat-field generator manual"),
    ("Panasonic CF-31", "Panasonic CF-31 manual"),
    ("The Sky Six Software", "TheSky Six software"),
    ("VisualSpec Software", "Visual Spec software"),
    ("SpecTrack Download", "SpecTrack download"),
    ("PlaneWave CDK Teleskop Instructions (setting spacing and collimation)", "PlaneWave CDK spacing and collimation instructions"),
    ("Delta-T Dew Heater for CDK", "Delta-T dew heater for CDK, manual"),
    ("Baader Solar Filter", "Baader solar-filter manual"),
    ("Coronado Solar Max II", "Coronado SolarMax II manual"),
    ("Model TCF-S", "TCF-S manual"),
    ("NexStar Hand Control", "NexStar hand-control manual"),
    ("SBIG Operating Manual CCD, ST7XE…", "SBIG CCD operating manual (ST-7XE etc.)"),
    ("SBIG’s AO7", "SBIG AO-7 manual"),
    ("BACHES manual (Deutsch)", "BACHES manual (German)"),
    ("BACHES manual (Englisch)", "BACHES manual (English)"),
    ("DADOS manual", "DADOS manual"),
    ("Bedienungsanleitung Neewer Kameraauslöser", "Neewer shutter-release manual"),
    ("Gebrauchsanweisung: Protective T-Ring (Canon EOS)", "Protective T-ring (Canon EOS) instructions"),
    ("Bedienungsanleitung SBIG CCD Kameras", "SBIG CCD camera manual"),
    ("STF 8300M/C CCD Camera Operation Manual", "STF-8300M/C CCD camera operation manual"),
    ("CCDOps V5", "CCDOps V5"),
    ("IDL", "IDL"),
    ("Tpoint", "TPoint"),
    ("RCU Koffer", "RCU case"),
    ("Schrauben", "Screws"),
    ("M3 Unterlegscheiben", "M3 washers"),
    ("M3/M4 Unterlegscheiben (5,3x10x1)", "M3/M4 washers 5.3×10×1"),
    ("M6 Unterlegscheiben D 120mm", "M6 washers, 120 mm"),
    ("M6 Unterlegscheiben D 180mm", "M6 washers, 180 mm"),
    ("M6 Unterlegscheiben D ?", "M6 washers, unknown diameter"),
    ("M12 Muttern", "M12 nuts"),
    ("M6 Muttern", "M6 nuts"),
    ("M5 Muttern", "M5 nuts"),
    ("M4 Muttern", "M4 nuts"),
    ("M3 Muttern", "M3 nuts"),
    ("M12x65mm Schraube", "M12×65 mm bolt"),
    ("M10x60mm Schraube", "M10×60 mm bolt"),
    ("M3x10mm Schraube", "M3×10 mm screws"),
    ("M3x16mm Schraube", "M3×16 mm screws"),
    ("M3x25mm Schraube", "M3×25 mm screws"),
    ("M6x16mm Schraube", "M6×16 mm screws"),
    ("M6x50mm Schrauben und passende Muttern", "M6×50 mm screws and matching nuts"),
    ("Sechskantschrauben M6x20", "M6×20 hex bolts"),
    ("Sechskantschrauben M6x16", "M6×16 hex bolts"),
    ("Sechskantschrauben M4x12", "M4×12 hex bolts"),
    ("M3x8mm Schrauben", "M3×8 mm screws"),
    ("4 Schrauben ehemals am C11 verbaut, schwarz", "Four black screws formerly on the C11"),
    ("Rohrschellen Gelenkrohrschellen 50-55 mm", "Hinged pipe clamps 50–55 mm"),
    ("Ösen M6x43", "M6×43 eye bolts"),
    ("Spannschloss 8mm", "8 mm turnbuckle"),
    ("CR2025 VARTA", "Varta CR2025 batteries"),
    ("LR44/V13GA VARTA", "Varta LR44/V13GA batteries"),
    ("LR41 (AG3) 1.5V", "LR41 (AG3) 1.5 V batteries"),
    ("CR2032", "CR2032 batteries"),
    ("USB-Stick mit Mauals", "USB sticks with manuals"),
]

WORD_MAP = {
    "und": "and",
    "für": "for",
    "mit": "with",
    "ohne": "without",
    "auf": "to",
    "von": "from",
    "der": "",
    "die": "",
    "das": "",
    "dem": "",
    "den": "",
    "des": "",
    "ein": "a",
    "eine": "a",
    "einer": "a",
    "klein": "small",
    "kleine": "small",
    "kleiner": "small",
    "gross": "large",
    "groß": "large",
    "grosse": "large",
    "große": "large",
    "großer": "large",
    "alt": "old",
    "alte": "old",
    "neu": "new",
    "neue": "new",
    "defekt": "defective",
    "gebraucht": "used",
    "verschiedene": "various",
    "verschiedener": "various",
    "unterschiedliche": "assorted",
    "kurze": "short",
    "kurzes": "short",
    "kurz": "short",
    "lange": "long",
    "schwarz": "black",
    "schwarze": "black",
    "weiß": "white",
    "weiss": "white",
    "rot": "red",
    "gelb": "yellow",
    "grün": "green",
    "blau": "blue",
    "grau": "grey",
    "Taschen": "bags",
    "Tasche": "bag",
    "Koffer": "case",
    "Zubehör": "accessories",
    "Objektiv": "lens",
    "Kamera": "camera",
    "Teleskop": "telescope",
    "Okular": "eyepiece",
    "Filter": "filter",
    "Kabel": "cable",
    "Netzteil": "power supply",
    "Schraube": "screw",
    "Muttern": "nuts",
    "Mutter": "nut",
    "Handbuch": "manual",
    "Handbücher": "manuals",
    "Werkzeug": "tool",
    "Adapterring": "adapter ring",
    "Distanzring": "spacer ring",
    "missing": "Missing",
}

DESC_SPLIT_RE = re.compile(
    r"^(?P<name>.+?)\s+[—–-]\s+(?P<desc>.+)$"
)

GERMAN_HINT = re.compile(
    r"\b(für|und|mit|ohne|Schraube|Tasche|Koffer|Netzteil|Okular|"
    r"Handbuch|Abdeck|Umlenk|Gewinde|Stecker|Buchse|Verlänger|"
    r"Reinig|Teleskop|Kamera|Filterrad|Montierung)\b",
    re.I,
)


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_td = False
        self.cell = []
        self.row = []
        self.rows = []
        self.cell_class = ""

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "tr":
            self.row = []
        elif tag == "td":
            self.in_td = True
            self.cell = []
            self.cell_class = attrs.get("class", "")

    def handle_endtag(self, tag):
        if tag == "td":
            text = " ".join("".join(self.cell).split())
            self.row.append((text, self.cell_class))
            self.in_td = False
            self.cell = []
        elif tag == "tr":
            if self.row:
                self.rows.append(self.row)
            self.row = []

    def handle_data(self, data):
        if self.in_td:
            self.cell.append(data)


def clip(text: str) -> str:
    text = " ".join((text or "").split())
    if len(text) <= MAX_FIELD:
        return text
    return text[: MAX_FIELD - 1].rstrip() + "…"


def tidy_inches(text: str) -> str:
    text = text.replace("¼", "1/4").replace("’’", '"').replace("''", '"')
    text = text.replace("“", '"').replace("”", '"').replace("’", "'")
    text = text.replace("‘", "'").replace("−", "-")
    text = re.sub(r"\b1\s*1/4\s*\"?", '1.25"', text)
    text = re.sub(r"\b2\s*\"", '2"', text)
    text = text.replace("×", "x")
    return text


def apply_phrases(text: str) -> str:
    text = tidy_inches(text)
    for src, dst in sorted(PHRASES, key=lambda pair: len(pair[0]), reverse=True):
        src_n = tidy_inches(src)
        if src_n.lower() in text.lower():
            text = re.compile(re.escape(src_n), re.I).sub(dst, text)
    return text


def leftover_german(text: str) -> str:
    words = {key.lower(): value for key, value in WORD_MAP.items()}
    parts = re.split(r"(\W+)", text)
    out = []
    for part in parts:
        mapped = words.get(part.lower())
        if mapped is None:
            out.append(part)
        elif mapped:
            if part[:1].isupper():
                out.append(mapped[:1].upper() + mapped[1:])
            else:
                out.append(mapped)
    return re.sub(r"\s{2,}", " ", "".join(out)).strip(" ,;/-")


def parse_quantity(raw: str):
    raw = (raw or "").strip().replace(",", ".")
    notes = []
    approx = False
    if not raw:
        return 1, False, notes
    lowered = raw.lower()
    if lowered in {"viele", "many"}:
        return 1, True, ["Quantity listed as many"]
    if raw[0] in "~>":
        approx = True
        raw = raw[1:].strip()
    try:
        value = float(raw)
    except ValueError:
        return 1, True, [f"Unparsed quantity {raw!r}"]
    if value <= 0:
        return 1, True, ["Original quantity was 0"]
    if not value.is_integer():
        return max(1, round(value)), True, notes
    return int(value), approx, notes


def parse_location(raw: str):
    raw = " ".join((raw or "").split())
    notes = []
    if raw in {"", "?"}:
        return "Unknown", ["Original location was unknown"]
    if raw == "OST/PRA":
        return "PRA", ["Listed as OST/PRA"]
    if raw == "PRA 2f/OST":
        return "PRA/2f", ["Also listed as OST"]
    if "," in raw:
        first, rest = raw.split(",", 1)
        notes.append(f"Also listed as {rest.strip()}")
        raw = first.strip()
    uncertain = raw.endswith("?")
    if uncertain:
        raw = raw[:-1].strip()
        notes.append("Location marked uncertain")
    raw = re.sub(r"\bAS\s+(\d)", r"AS\1", raw, flags=re.I)
    raw = re.sub(r"\bRC\s+(\d)", r"RC\1", raw, flags=re.I)
    raw = re.sub(r"\bRS\s+(\d)", r"RS\1", raw, flags=re.I)
    match = re.match(r"^(PRA|OST|KRA|RRA)\s+(.+)$", raw, re.I)
    if match:
        room = match.group(1).upper()
        place = match.group(2).strip()
        if re.fullmatch(r"\d+[A-Za-z]", place):
            place = place[:-1] + place[-1].lower()
        elif re.match(r"^(RC|AS|D|RS)\d", place, re.I):
            letters = re.match(r"^[A-Za-z]+", place).group()
            place = letters.upper() + place[len(letters) :]
            if place.upper() == "RS4":
                notes.append("Original place was RS4")
                place = "RC4"
        if room == "PRA" and place == "23":
            notes.append("Original place was 23")
            return "PRA", notes
        return f"{room}/{place}", notes
    match = re.match(r"^(PRA|OST|KRA|RRA)$", raw, re.I)
    if match:
        return match.group(1).upper(), notes
    return "Unknown", notes + [f"Unparsed location {raw!r}"]


def cat_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def map_category(raw: str) -> list[str]:
    key = cat_key(raw)
    if key in SKIP_CATS:
        return []
    if key == "qhy268m, qhy600m":
        return ["QHY268M", "QHY600M"]
    if key == "c11 / c14":
        return ["C11", "C14"]
    mapped = CAT_MAP.get(key)
    return [mapped] if mapped else []


def categories_for(section: str, raw_cats: list[str], name: str) -> list[str]:
    ordered = []
    section_cat = SECTION_CATEGORY.get(section)
    if section_cat:
        ordered.append(section_cat)
    for raw in raw_cats:
        ordered.extend(map_category(raw))
    upper = name.upper()
    for needle, extra in NAME_KEYWORDS:
        if needle.upper() in upper:
            if extra == "Canon 700D" and "CANON" not in upper and "700D" not in upper:
                continue
            ordered.append(extra)
    seen = set()
    unique = []
    for cat in ordered:
        if not cat or cat in seen:
            continue
        seen.add(cat)
        unique.append(cat)
        if len(unique) == MAX_CATS:
            break
    if not unique:
        unique = ["Accessory"]
    return unique


def translate_container(raw: str) -> str:
    raw = " ".join((raw or "").split())
    if not raw:
        return ""
    mapped = CONTAINER_MAP.get(raw.lower())
    if mapped:
        return mapped
    text = apply_phrases(raw)
    text = leftover_german(text)
    return tidy_inches(text)


def split_name(original: str) -> tuple[str, str]:
    original = " ".join(original.split())
    description = ""
    name = apply_phrases(original)
    name = tidy_inches(name)
    if name == original:
        match = re.fullmatch(r"(.+?) \(([^()]{20,})\)$", name)
        if match and len(match.group(1)) >= 12:
            name, description = match.group(1), match.group(2)
        else:
            match = DESC_SPLIT_RE.match(name)
            if match and len(match.group("name")) >= 8 and len(match.group("desc")) >= 16:
                name, description = match.group("name"), match.group("desc")
    name = leftover_german(name)
    description = leftover_german(description)
    name = tidy_inches(name)
    description = tidy_inches(description)
    name = re.sub(r"\s{2,}", " ", name).strip(" -–,")
    description = re.sub(r"\s{2,}", " ", description).strip(" -–,")
    if name.lower() == description.lower():
        description = ""
    if not description:
        match = re.match(r"^(.{16,}?), with (.+)$", name, re.I)
        if match:
            name, description = match.group(1).strip(), "With " + match.group(2).strip()
    if len(name) > 90 and not description:
        cut = name.find(", ")
        if 20 < cut < 80:
            description = name[cut + 2 :].strip()
            name = name[:cut].strip()
    return name, description


def polish_english(text: str) -> str:
    text = re.sub(r"\binstalled am\b", "Installed on the", text, flags=re.I)
    text = re.sub(r"\binstalled an der\b", "Installed on the", text, flags=re.I)
    text = re.sub(r"\binstalled an\b", "Installed on the", text, flags=re.I)
    text = re.sub(r"\bwahrscheinlich am\b", "Probably on the", text, flags=re.I)
    text = re.sub(r"\bwahrscheinlich\b", "probably", text, flags=re.I)
    text = re.sub(r"\behemals am\b", "Formerly on", text, flags=re.I)
    text = text.replace("Schnellwechsler", "quick changer")
    text = text.replace("Kalibrationseinheit", "calibration unit")
    text = text.replace("Tengentialneiger", "tangent assembly")
    text = text.replace("Tangentialneiger", "tangent assembly")
    text = text.replace("Spiralkabel", "coiled cable")
    return re.sub(r"\s{2,}", " ", text).strip(" ;,")


def translate_comment(raw: str) -> str:
    raw = " ".join((raw or "").split())
    if not raw:
        return ""
    replacements = [
        ("(verbaut)", "Installed"),
        ("ehemals am BACHES verbaut", "Formerly installed on BACHES"),
        ("wahrscheinlich am Raspberry Pi 5 verbaut", "Probably installed on the Raspberry Pi 5"),
        ("verbaut in Wetterstation", "Installed in the weather station"),
        ("für Wetterstation", "For the weather station"),
        ("OST Teleskop (verbaut)", "Installed on the OST telescope"),
        ("verbaut am RASA", "Installed on the RASA"),
        ("verbaut: BAChES & DADOS", "Installed on BACHES and DADOS"),
        ("QHYCFW3L verbaut", "Installed on QHYCFW3L"),
        ("verbaut am Tengentialneiger", "Installed on the tangent assembly"),
        ("verbaut an der Kalibrationseinheit", "Installed on the calibration unit"),
        ("mounted to the C14 guide scope", "Mounted to the C14 guide scope"),
        ("Mounted to C11", "Mounted to the C11"),
        ("mounted to the BSPS", "Mounted to the BSPS"),
        ("one mounted to the BSPS", "One mounted to the BSPS"),
        ("mounted to TS-Optics Starscope 80/600 mm", "Mounted to TS-Optics Starscope 80/600 mm"),
        ("mounted to PHOTOLINE 130 mm", "Mounted to the PHOTOLINE 130 mm"),
        ("verbaut am APO", "Installed on the APO"),
        ("verbaut am OST", "Installed on the OST telescope"),
        ("verbaut am Rasa", "Installed on the RASA"),
        ("OST verbaut", "Installed on the OST telescope"),
        ("APO verbaut", "Installed on the APO"),
        ("C14 verbaut", "Installed on the C14"),
        ("verbaut", "installed"),
    ]
    text = raw
    for src, dst in sorted(replacements, key=lambda pair: len(pair[0]), reverse=True):
        text = re.compile(re.escape(src), re.I).sub(dst, text)
    text = apply_phrases(text)
    text = leftover_german(text)
    text = tidy_inches(text)
    text = clip(polish_english(text))
    if text.lower() == "installed":
        return "Installed"
    if text.lower() == "missing":
        return "Missing"
    return text


def dedupe_notes(parts: list[str]) -> list[str]:
    kept = []
    for part in parts:
        part = polish_english(part)
        if not part:
            continue
        key = re.sub(r"[^a-z0-9]+", "", part.lower())
        if any(
            key in re.sub(r"[^a-z0-9]+", "", existing.lower())
            or re.sub(r"[^a-z0-9]+", "", existing.lower()) in key
            for existing in kept
        ):
            continue
        kept.append(part)
    return kept


def parse_rows(html: str) -> list[dict]:
    parser = TableParser()
    parser.feed(html)
    items = []
    section = ""
    for row in parser.rows[1:]:
        cells = [cell[0] for cell in row[:9]]
        cls = row[0][1] if row else ""
        name = cells[0] if cells else ""
        qty = cells[1] if len(cells) > 1 else ""
        loc = cells[2] if len(cells) > 2 else ""
        container = cells[3] if len(cells) > 3 else ""
        cats = [cells[i] for i in range(4, 8) if len(cells) > i and cells[i]]
        comment = cells[8] if len(cells) > 8 else ""
        is_section = ("ce33" in cls or "ce10" in cls) and (name.endswith(":") or not qty)
        if is_section and name:
            section = name.rstrip(":")
            continue
        if not name:
            continue
        items.append(
            {
                "section": section,
                "name": name,
                "qty": qty,
                "loc": loc,
                "container": container,
                "cats": cats,
                "comment": comment,
            }
        )
    return items


def convert_item(raw: dict) -> dict:
    notes = []
    qty, approx, qty_notes = parse_quantity(raw["qty"])
    notes.extend(qty_notes)
    location, loc_notes = parse_location(raw["loc"])
    notes.extend(loc_notes)
    name, description = split_name(raw["name"])
    comment_parts = []
    translated_comment = translate_comment(raw["comment"])
    if translated_comment:
        comment_parts.append(translated_comment)
    elif re.search(r"verbaut|mounted to", raw["name"], re.I) and not re.search(
        r"install|formerly|mounted", name, re.I
    ):
        from_name = translate_comment(raw["name"])
        if from_name and from_name.lower() != name.lower():
            comment_parts.append(from_name)
    comment_parts.extend(notes)
    comment_parts = dedupe_notes(comment_parts)
    cats = categories_for(raw["section"], raw["cats"], f"{name} {raw['name']}")
    project = SECTION_PROJECT.get(raw["section"], "")
    return {
        "name": clip(name or "Unnamed item"),
        "location_path": location,
        "quantity": str(qty),
        "quantity_approximate": "yes" if approx else "",
        "container": clip(translate_container(raw["container"])),
        "categories": ";".join(cats),
        "description": clip(description),
        "comment": clip("; ".join(p for p in comment_parts if p)),
        "project": project,
    }


def disambiguate(rows: list[dict]) -> None:
    seen: dict[tuple[str, str], int] = {}
    for row in rows:
        key = (row["name"].lower(), row["location_path"])
        count = seen.get(key, 0) + 1
        seen[key] = count
        if count > 1:
            row["name"] = clip(f"{row['name']} ({count})")


def remaining_german(rows: list[dict]) -> list[str]:
    hits = []
    for row in rows:
        blob = " ".join(row[k] for k in ("name", "description", "comment", "container"))
        if GERMAN_HINT.search(blob):
            hits.append(row["name"])
    return hits


def main() -> None:
    html = SOURCE.read_text(encoding="utf-8")
    converted = [convert_item(raw) for raw in parse_rows(html)]
    disambiguate(converted)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "name",
        "location_path",
        "quantity",
        "quantity_approximate",
        "container",
        "categories",
        "description",
        "comment",
        "project",
    ]
    with OUTPUT.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(converted)
    leftover = remaining_german(converted)
    cats = {}
    locs = {}
    for row in converted:
        locs[row["location_path"]] = locs.get(row["location_path"], 0) + 1
        for cat in row["categories"].split(";"):
            cats[cat] = cats.get(cat, 0) + 1
    print(f"Wrote {len(converted)} rows to {OUTPUT}")
    print(f"Locations: {len(locs)}")
    print("Top categories:")
    for cat, n in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))[:25]:
        print(f"  {n:4} {cat}")
    print(f"Names still looking German: {len(leftover)}")
    for name in leftover[:40]:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
