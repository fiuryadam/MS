from gps_data import GpsData


def nmea_checksum(data):
    value = 0
    for ch in data:
        value ^= ord(ch)
    return f"{value:02X}"


class NmeaParser:
    def __init__(self):
        self.last_date = None
        self.current = None
        self.current_key = None
        self.gap = False
        self.segments = []

    def parse_line(self, line):
        line = line.strip()
        if not line.startswith("$"):
            return None

        body = line[1:]
        if "*" in body:
            payload, given = body.rsplit("*", 1)
            given = given.strip()[:2]
            if given and given.upper() != nmea_checksum(payload):
                return None
            fields = payload.split(",")
        else:
            fields = body.split(",")

        if not fields or len(fields[0]) < 3:
            return None
        return fields[0][-3:], fields[1:]

    def feed(self, line):
        parsed = self.parse_line(line)
        if not parsed:
            return
        stype, fields = parsed

        if stype in ("GGA", "RMC"):
            new_key = fields[0] if fields else None
            if new_key and self.current is not None and self.current_key and new_key != self.current_key:
                self.flush()
            if self.current is None:
                self.current = GpsData()
            if new_key:
                self.current_key = new_key
                self.current.time_key = new_key
            if stype == "GGA":
                self.current.apply_gga(fields, self.last_date)
            else:
                self.last_date = self.current.apply_rmc(fields, self.last_date)
        elif self.current is not None:
            if stype == "GSA":
                self.current.apply_gsa(fields)
            elif stype == "VTG":
                self.current.apply_vtg(fields)

    def flush(self):
        if self.current is None:
            return
        if self.current.is_valid():
            if self.gap or not self.segments:
                self.segments.append([])
                self.gap = False
            self.segments[-1].append(self.current)
        else:
            self.gap = True
        self.current = None
        self.current_key = None

    def parse_file(self, path):
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            for line in handle:
                self.feed(line)
        self.flush()
        return self.segments
