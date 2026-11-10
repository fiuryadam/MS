import math
from datetime import datetime, timezone

EARTH_RADIUS_M = 6371000.0

def nmea_to_deg(value, hemi):
    if not value or not hemi:
        return None
    raw = float(value)
    degrees = int(raw // 100)
    minutes = raw - degrees * 100
    result = degrees + minutes / 60.0
    if hemi in ("S", "W"):
        result = -result
    return result

def parse_time(text):
    if not text:
        return None
    if "." in text:
        head, frac = text.split(".", 1)
        frac = (frac + "000000")[:6]
    else:
        head = text
        frac = "000000"
    if len(head) < 6:
        return None
    hour = int(head[0:2])
    minute = int(head[2:4])
    second = int(head[4:6])
    micro = int(frac)
    return hour, minute, second, micro

def parse_date(text):
    if not text or len(text) < 6:
        return None
    day = int(text[0:2])
    month = int(text[2:4])
    year = int(text[4:6])
    if year < 80:
        year += 2000
    else:
        year += 1900
    return year, month, day

def build_datetime(date_parts, time_parts):
    if not date_parts or not time_parts:
        return None
    year, month, day = date_parts
    hour, minute, second, micro = time_parts
    return datetime(year, month, day, hour, minute, second, micro, tzinfo=timezone.utc)

def parse_magvar(value, direction):
    if not value:
        return None
    angle = float(value)
    if direction == "W":
        angle = -angle
    return angle

def haversine(lat1, lon1, lat2, lon2):
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))

def bearing(lat1, lon1, lat2, lon2):
    lat1_r = math.radians(lat1)
    lat2_r = math.radians(lat2)
    dlon = math.radians(lon2 - lon1)
    y = math.sin(dlon) * math.cos(lat2_r)
    x = math.cos(lat1_r) * math.sin(lat2_r) - math.sin(lat1_r) * math.cos(lat2_r) * math.cos(dlon)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0

class GpsData:
    def __init__(self):
        self.time_key = None
        self.dt = None
        self.lat = None
        self.lon = None
        self.ele = None
        self.geoidheight = None
        self.magvar = None
        self.gga_quality = None
        self.rmc_status = None
        self.gsa_fix = None
        self.sat = None
        self.hdop = None
        self.vdop = None
        self.pdop = None
        self.ageofdgpsdata = None
        self.dgpsid = None
        self.speed = None
        self.course = None
        self.satellites = []

    def apply_gga(self, fields, last_date=None):
        if len(fields) < 10:
            return
        time_parts = parse_time(fields[0])
        if time_parts:
            self.time_key = fields[0]
            if last_date and self.dt is None:
                self.dt = build_datetime(last_date, time_parts)
        lat = nmea_to_deg(fields[1], fields[2])
        lon = nmea_to_deg(fields[3], fields[4])
        if lat is not None:
            self.lat = lat
        if lon is not None:
            self.lon = lon
        if fields[5]:
            self.gga_quality = int(fields[5])
        if fields[6]:
            self.sat = int(fields[6])
        if fields[7]:
            self.hdop = float(fields[7])
        if fields[8]:
            self.ele = float(fields[8])
        if len(fields) > 10 and fields[10]:
            self.geoidheight = float(fields[10])
        if len(fields) > 12 and fields[12]:
            self.ageofdgpsdata = float(fields[12])
        if len(fields) > 13 and fields[13]:
            self.dgpsid = int(fields[13])

    def apply_rmc(self, fields, last_date=None):
        if len(fields) < 9:
            return last_date
        time_parts = parse_time(fields[0])
        if time_parts:
            self.time_key = fields[0]
        self.rmc_status = fields[1] or None
        lat = nmea_to_deg(fields[2], fields[3])
        lon = nmea_to_deg(fields[4], fields[5])
        if lat is not None:
            self.lat = lat
        if lon is not None:
            self.lon = lon
        date_parts = parse_date(fields[8])
        if date_parts:
            last_date = date_parts
        if time_parts:
            self.dt = build_datetime(last_date, time_parts)
        if len(fields) > 6 and fields[6]:
            self.speed = float(fields[6]) * 1852.0 / 3600.0
        if len(fields) > 7 and fields[7]:
            self.course = float(fields[7])
        if len(fields) > 9 and fields[9]:
            direction = fields[10] if len(fields) > 10 else ""
            self.magvar = parse_magvar(fields[9], direction)
        return last_date

    def apply_gsa(self, fields):
        if len(fields) < 17:
            return
        if fields[1]:
            self.gsa_fix = int(fields[1])
        if fields[14]:
            self.pdop = float(fields[14])
        if fields[15] and self.hdop is None:
            self.hdop = float(fields[15])
        if fields[16]:
            self.vdop = float(fields[16])

    def apply_gsv(self, fields):
        i = 3
        while i < len(fields) and fields[i]:
            prn, elev, azim, snr = (fields + ["", "", ""])[i:i + 4]
            self.satellites.append((
                int(prn),
                int(elev) if elev else None,
                int(azim) if azim else None,
                int(snr) if snr else None,
            ))
            i += 4

    def apply_vtg(self, fields):
        if len(fields) > 0 and fields[0]:
            self.course = float(fields[0])
        if len(fields) > 4 and fields[4]:
            self.speed = float(fields[4]) * 1852.0 / 3600.0
        elif len(fields) > 6 and fields[6]:
            self.speed = float(fields[6]) / 3.6

    def is_valid(self):
        if self.lat is None or self.lon is None:
            return False
        if self.gga_quality == 0:
            return False
        if self.rmc_status == "V":
            return False
        return True

    def gpx_fix(self):
        if self.gga_quality == 3:
            return "pps"
        if self.gga_quality == 2:
            return "dgps"
        if self.gsa_fix == 1:
            return "none"
        if self.gsa_fix == 2:
            return "2d"
        if self.gsa_fix == 3:
            return "3d"
        return None

    def distance_to(self, other):
        return haversine(self.lat, self.lon, other.lat, other.lon)

    def bearing_to(self, other):
        return bearing(self.lat, self.lon, other.lat, other.lon)
