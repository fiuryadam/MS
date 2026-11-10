from xml.etree import ElementTree as ET

GPX_NS = "http://www.topografix.com/GPX/1/1"
NMEA_NS = "http://trekbuddy.net/2009/01/gpx/nmea"

class GpxWriter:
    def add_child(self, parent, tag, text):
        child = ET.SubElement(parent, tag)
        child.text = text
        return child

    def append_trkpt(self, parent, point):
        trkpt = ET.SubElement(
            parent,
            "trkpt",
            {
                "lat": f"{point.lat:.6f}",
                "lon": f"{point.lon:.6f}",
            },
        )
        if point.ele is not None:
            self.add_child(trkpt, "ele", f"{point.ele:.1f}")
        if point.dt is not None:
            self.add_child(trkpt, "time", point.dt.strftime("%Y-%m-%dT%H:%M:%SZ"))
        if point.magvar is not None:
            self.add_child(trkpt, "magvar", f"{point.magvar:.1f}")
        if point.geoidheight is not None:
            self.add_child(trkpt, "geoidheight", f"{point.geoidheight:.1f}")
        fix = point.gpx_fix()
        if fix:
            self.add_child(trkpt, "fix", fix)
        if point.sat is not None:
            self.add_child(trkpt, "sat", str(point.sat))
        if point.hdop is not None:
            self.add_child(trkpt, "hdop", f"{point.hdop:.1f}")
        if point.vdop is not None:
            self.add_child(trkpt, "vdop", f"{point.vdop:.1f}")
        if point.pdop is not None:
            self.add_child(trkpt, "pdop", f"{point.pdop:.1f}")
        if point.ageofdgpsdata is not None:
            self.add_child(trkpt, "ageofdgpsdata", f"{point.ageofdgpsdata:.1f}")
        if point.dgpsid is not None:
            self.add_child(trkpt, "dgpsid", str(point.dgpsid))
        if point.speed is not None or point.course is not None:
            ext = ET.SubElement(trkpt, "extensions")
            if point.speed is not None:
                self.add_child(ext, f"{{{NMEA_NS}}}speed", f"{point.speed:.2f}")
            if point.course is not None:
                self.add_child(ext, f"{{{NMEA_NS}}}course", f"{point.course:.1f}")

    def write(self, path, segments):
        ET.register_namespace("", GPX_NS)
        ET.register_namespace("nmea", NMEA_NS)
        root = ET.Element(
            "gpx",
            {
                "xmlns": GPX_NS,
                "version": "1.1",
                "creator": "nmea2gpx",
            },
        )
        trk = ET.SubElement(root, "trk")
        ET.SubElement(trk, "name").text = "NMEA track"

        for segment in segments:
            if not segment:
                continue
            trkseg = ET.SubElement(trk, "trkseg")
            for point in segment:
                self.append_trkpt(trkseg, point)

        tree = ET.ElementTree(root)
        if hasattr(ET, "indent"):
            ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)
