def heading_delta(a, b):
    diff = abs(a - b) % 360.0
    if diff > 180.0:
        diff = 360.0 - diff
    return diff


class TrackFilter:
    def __init__(self, min_time=0, min_heading=0, min_distance=0):
        self.min_time = min_time
        self.min_heading = min_heading
        self.min_distance = min_distance

    def enabled(self):
        return self.min_time > 0 or self.min_heading > 0 or self.min_distance > 0

    def keep(self, candidate, kept):
        if not kept:
            return True
        if not self.enabled():
            return True

        last = kept[-1]
        if self.min_time > 0 and candidate.dt and last.dt:
            if abs((candidate.dt - last.dt).total_seconds()) >= self.min_time:
                return True

        if self.min_distance > 0:
            if last.distance_to(candidate) >= self.min_distance:
                return True

        if self.min_heading > 0:
            if len(kept) == 1 and self.min_time == 0 and self.min_distance == 0:
                return True
            if len(kept) >= 2:
                prev = kept[-2]
                b_prev = prev.bearing_to(last)
                b_now = last.bearing_to(candidate)
                if heading_delta(b_prev, b_now) >= self.min_heading:
                    return True

        return False

    def apply(self, segments):
        result = []
        for segment in segments:
            kept = []
            for point in segment:
                if self.keep(point, kept):
                    kept.append(point)
            if kept:
                result.append(kept)
        return result
