import concurrent.futures
import math
import os
import traceback
import urllib
import zlib
from urllib.request import urlopen, Request
import json
import re
import chardet
import urllib.parse


def get_json(url):
    response = urlopen(url)
    return json.loads(response.read())


def get_text(url, gzip=True):
    req = Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36')
    if gzip:
        req.add_header('Accept-Encoding', 'gzip')
    req.add_header('Accept', 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7')
    req.add_header('Connection', 'keep-alive')
    response = urlopen(req)
    text = response.read()
    encoding = chardet.detect(text)
    if encoding['encoding'] is None:
        decompressed_data = zlib.decompress(text, 16 + zlib.MAX_WBITS)
        return str(decompressed_data)
    else:
        return text.decode(encoding['encoding'])


def get_all_routes_data():
    return get_json("https://data.etabus.gov.hk/v1/transport/kmb/route/")["data"]


def get_all_routes():
    return set([x["route"] for x in get_all_routes_data()])


def resolve_bbi_data(data):
    result = {}
    for route_number, route_data in data.items():
        route_result = []
        bbi_routes = route_data["Records"]
        bbi_direction = route_data["bus_arr"][0]["dest"]
        for bbi_route in bbi_routes:
            bbi_route_number = bbi_route["sec_routeno"]
            destination = bbi_route["sec_dest"]
            max_change = int(bbi_route["success_cnt"])
            time_limit_raw = bbi_route["validity"]
            time_limit = 0
            if time_limit_raw == "^":
                time_limit = 30
            elif time_limit_raw == "#":
                time_limit = 60
            elif time_limit_raw == "*":
                time_limit = 90
            elif time_limit_raw == "@":
                time_limit = 120
            elif time_limit_raw == "":
                time_limit = 150
            recommended_bbi = bbi_route["xchange"]
            discount_raw = bbi_route["discount_max"]
            discount_type = "error"
            discount = -1
            if "免費" in discount_raw:
                discount_type = "free"
                discount = 0
            elif re.match("減 \$([0-9.]+)", discount_raw):
                discount_type = "discount"
                discount = float(re.search("減 \$([0-9.]+)", discount_raw).group(1))
            elif re.match("兩程合共 \$([0-9.]+)", discount_raw):
                discount_type = "combined_fare"
                discount = float(re.search("兩程合共 \$([0-9.]+)", discount_raw).group(1))
            elif re.match("付 \$([0-9.]+)", discount_raw):
                discount_type = "fixed_fare"
                discount = float(re.search("付 \$([0-9.]+)", discount_raw).group(1))
            elif re.match("回贈 \$([0-9.]+)", discount_raw):
                discount_type = "return"
                discount = float(re.search("回贈 \$([0-9.]+)", discount_raw).group(1))
            else:
                print(discount_raw)
            bbi_route_result = {
                "bbi_direction": bbi_direction,
                "bbi_route_number": bbi_route_number,
                "destination": destination,
                "max_change": max_change,
                "time_limit": time_limit,
                "recommended_bbi": recommended_bbi,
                "discount_type": discount_type,
                "discount": discount,
                "discount_raw": discount_raw}
            route_result.append(bbi_route_result)
        result[route_number] = route_result
    return result


def resolve_regional_two_way_section_fare(data):
    routes = []
    routes_done = []
    pattern = "(?:<t(?:r| |r )>|<tr class=\"table-even-row\">)(?:[\n\r\s]|.)*?<td(?: rowspan=\"2\")?>([0-9]+.)(?: <br>（包括特別班）)?<\/td>(?:[\n\r\s]|.)*?<td>([^ <往]+)(?:往.*)? *至 *([^ <*]+)(?:\*[^<]*)? *(?:</br>(?:[\n\r\s]|.)*?([^ <\n\r\s]+)? *至 *([^ <]+) *)?</td>(?:[\n\r\s]|.)*?<td(?: rowspan=\"2\")?>\$([0-9.]+)\*?</td>(?:[\n\r\s]|.)*?</tr>"
    itr = re.finditer(pattern, data, flags=0)
    for matcher in itr:
        route_number = matcher.group(1)
        start = matcher.group(2).strip()
        end = matcher.group(3).strip()
        fare = float(matcher.group(6))
        route_result = {
            "route_number": route_number,
            "start": start,
            "end": end,
            "fare": fare}
        routes.append(route_result)

        if matcher.group(4) is not None:
            alt_start = matcher.group(4).strip()
            alt_end = matcher.group(5).strip()
            route_result = {
                "route_number": route_number,
                "start": alt_start,
                "end": alt_end,
                "fare": fare}
            routes.append(route_result)

        routes_done.append(route_number)

    all_routes = get_all_routes()
    for n in all_routes:
        if n not in routes_done:
            print(n)
            special_data = get_json("https://search.kmb.hk/KMBWebSite/Function/FunctionRequest.ashx?action=getAnnounce&route=%s&bound=1".replace("%s", n))["data"]
            for entry in special_data:
                if entry["kpi_title_chi"] == "八達通分段收費":
                    url = entry["kpi_noticeimageurl"]
                    announcement = get_text("https://search.kmb.hk/KMBWebSite/AnnouncementPicture.ashx?url=" + url)
                    pattern = "<li>.*?([^ 往]*).*?至.*?([^ 往]*).*?</li>(?:[\n\r\s]|.)*?</td>(?:[\n\r\s]|.)*?.+\$([0-9.]+)</td>"
                    itr = re.finditer(pattern, announcement, flags=0)
                    for matcher in itr:
                        start = matcher.group(1).strip()
                        end = matcher.group(2).strip()
                        fare = float(matcher.group(3))
                        route_result = {
                            "route_number": n,
                            "start": start,
                            "end": end,
                            "fare": fare}
                        routes.append(route_result)

    area = ["屯門", "元朗", "天水圍", "將軍澳", "西貢區", "北區", "粉嶺", "大埔", "旺角"]

    return {"area": area, "routes": routes}


def haversine_distance(lat1, lon1, lat2, lon2):
    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    d_lat = lat2_rad - lat1_rad
    d_lon = lon2_rad - lon1_rad

    a = math.sin(d_lat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(d_lon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return 6371.0 * c


def find_first_closest_location_index(location, locations):
    closest_distance = haversine_distance(location[0], location[1], locations[0][0], locations[0][1])
    closest_index = -1
    for i in range(1, len(locations)):
        loc = locations[i]
        distance = haversine_distance(location[0], location[1], loc[0], loc[1])
        if distance <= closest_distance:
            closest_distance = distance
            closest_index = i
        elif closest_index >= 0 and closest_distance <= 0.2:
            return closest_index
    return (len(locations) - 1) if closest_index < 0 else closest_index


def find_closest_section(location, sections):
    closest = None
    closest_distance = -1
    for path in sections:
        for loc in path:
            distance = haversine_distance(location[0], location[1], loc[0], loc[1])
            if closest_distance < 0 or distance < closest_distance:
                closest = path
                closest_distance = distance
    return closest


def sort_sections(sections):
    pool = list(sections[1:])
    result = [sections[0]]
    location = sections[0][0]
    while len(pool) > 0:
        closest = find_closest_section(location, pool)
        pool.remove(closest)
        result.append(closest)
        location = closest[0]
    return result


def kmb_route_exists(route):
    for kmb_route in kmb_route_list:
        if route["route"] == kmb_route["route"] and route["bound"]["kmb"] == kmb_route["bound"] and route["serviceType"] == kmb_route["service_type"] and route["orig"]["zh"].replace("／", "/") == kmb_route["orig_tc"].replace("／", "/") and route["dest"]["zh"].replace("／", "/") == kmb_route["dest_tc"].replace("／", "/"):
            return True
    return False


def resolve_route_information(data, stops):
    result = []
    pattern = "<coordinates> *(.*?) *<\/coordinates>"
    itr = re.finditer(pattern, data, flags=0)
    for matcher in itr:
        sub_result = []
        text = matcher.group(1)
        pattern_2 = "([0-9.]+),([0-9.]+),(?:[0-9.]+)"
        itr_2 = re.finditer(pattern_2, text, flags=0)
        for matcher_2 in itr_2:
            sub_result.append([float(matcher_2.group(2)), float(matcher_2.group(1))])
        result.append(sub_result)
    sorted_result = sort_sections(result)
    combined = []
    for section in sorted_result:
        combined = section + combined
    combined.reverse()
    if len(stops) <= 1:
        return [combined]
    result = []
    for i in range(1, len(stops) - 1):
        stop = data_sheet["stopList"][stops[i]]
        location = [stop["location"]["lat"], stop["location"]["lng"]]
        index = find_first_closest_location_index(location, combined)
        result.append(combined[:(index + 1)])
        del combined[:index]
    result.append(combined)
    return result


def read_ctb_bbi():
    result = []
    for i in range(2, 95):
        print(i)
        tc_data = get_json(ctb_bbi_tc_url + str(i))
        en_data = get_json(ctb_bbi_en_url + str(i))
        for u in range(0, len(tc_data)):
            entry = tc_data[u]
            entry["remarkEn"] = en_data[u]["remark"]
            result.append(entry)
    write_dict_to_file("data/ctb_bbi_data.json", result)


def add_route_path(route_number, route_data):
    print(route_number)
    route_paths = {}
    for entry in route_data:
        if entry["route"] == route_number:
            stops = None
            for key, route in data_sheet["routeList"].items():
                if "kmb" in route["bound"] and kmb_route_exists(route) and route["route"] == route_number and entry["bound"] == route["bound"]["kmb"] and entry["service_type"] == route["serviceType"]:
                    stops = route["stops"]["kmb"]
                    break
            b = resolve_route_information(get_text(paths_url.replace("{route}", route_number).replace("{bound}", "1" if entry["bound"] == "O" else "2").replace("{type}", entry["service_type"])), stops)
            if entry["bound"] not in route_paths:
                route_paths[entry["bound"]] = {}
            route_paths[entry["bound"]][entry["service_type"]] = b
    write_dict_to_file("data/route_paths\\" + route_number + ".json", route_paths)


def resolve_mtr_bus_data():
    routes_result = {}
    stops_result = {}
    stops_alias_result = {}
    stop_entries = [[y[1:len(y) - 1] if y.startswith("\"") else y for y in x.split(",")] for x in mtr_bus_stop_list.splitlines()[1:]]
    route_entries = [[y[1:len(y) - 1] if y.startswith("\"") else y for y in x.split(",")] for x in mtr_bus_route_list.splitlines()[1:]]
    fares_entries = [[y[1:len(y) - 1] if y.startswith("\"") else y for y in x.split(",")] for x in mtr_bus_fare_list.splitlines()[1:]]

    stops_map = {}
    stops_by_route_bound = {}
    for stop_entry in stop_entries:
        position = stop_entry[4] + " " + stop_entry[5]
        if position not in stops_map:
            stops_map[position] = [stop_entry[3], stop_entry]
            stops_alias_result[stop_entry[3]] = [stop_entry[3]]
        else:
            stops_alias_result[stops_map[position][0]].append(stop_entry[3])
        route_number = stop_entry[0]
        bound = stop_entry[1]
        key = route_number + "_" + bound
        if key in stops_by_route_bound:
            stops_by_route_bound[key].append(stop_entry)
        else:
            stops_by_route_bound[key] = [stop_entry]

    for key, stop_details in stops_map.items():
        position = [float(stop_details[1][4]), float(stop_details[1][5])]
        result = {
            "location": {
                "lat": position[0],
                "lng": position[1]
            },
            "name": {
                "en": stop_details[1][7].upper(),
                "zh": stop_details[1][6]
            }
        }
        stops_result[stop_details[1][3]] = result

    for route_entry in route_entries:
        route_number = route_entry[0]
        for bound in ["O", "I"]:
            key = route_number + "_" + bound
            if key in stops_by_route_bound:
                stop_list = stops_by_route_bound[key]
                stop_list.sort(key=lambda x: float(x[2]))
                stop_ids = []
                for stop in stop_list:
                    position = stop[4] + " " + stop[5]
                    stop_ids.append(stops_map[position][0])
                fares = [next(x for x in fares_entries if x[0] == route_number)[1]] * len(stop_ids)
                result = {
                    "bound": {
                        "mtr-bus": bound
                    },
                    "co": [
                        "mtr-bus"
                    ],
                    "dest": {
                        "en": route_entry[2].split(" to ")[1].upper() if bound == "O" else stop_list[-1][7].upper(),
                        "zh": route_entry[1].split("至")[1] if bound == "O" else stop_list[-1][6]
                    },
                    "fares": fares,
                    "faresHoliday": None,
                    "freq": None,
                    "gtfsId": None,
                    "jt": None,
                    "nlbId": None,
                    "orig": {
                        "en": stop_list[0][7].upper(),
                        "zh": stop_list[0][6]
                    },
                    "route": route_number,
                    "seq": -1,
                    "serviceType": 1,
                    "stops": {
                        "mtr-bus": stop_ids
                    }
                }
                key = route_number + "+1+" + stop_list[0][7] + "+" + stop_list[-1][7]
                routes_result[key] = result

    write_dict_to_file("data/mtr_bus_routes.json", routes_result)
    write_dict_to_file("data/mtr_bus_stops.json", stops_result)
    write_dict_to_file("data/mtr_bus_stop_alias.json", stops_alias_result)


def get_ctb_paths(data):
    result = {}
    for route_number, route_data in data.items():
        print(route_number)
        result[route_number] = {}
        for bound, bound_data in route_data.items():
            result[route_number][bound] = {}
            for variant, variant_data in bound_data["variants"].items():
                url = ctb_path_url + urllib.parse.quote(variant_data["longId"], safe='/', encoding=None, errors=None)
                print(url)
                route_path = get_text(url)
                positions = []
                for m in re.finditer(re.compile(r'[0-9.]+,([0-9.]+),([0-9.]+)'), route_path):
                    positions.append([float(m.group(1)), float(m.group(2))])
                result[route_number][bound][variant] = positions
    return result


def get_all_ctb_stop_pairs(route_number, bound):
    result = set()
    for key, data in data_sheet["routeList"].items():
        if data["route"] == route_number and "ctb" in data["bound"] and (len(data["bound"]["ctb"]) > 1 or data["bound"]["ctb"] == bound):
            stops = data["stops"]["ctb"]
            for i in range(0, len(stops) - 1):
                result.add(stops[i] + "+" + stops[i + 1])
    return result


def find_trim_closest_section(path, stop_1, stop_2):
    shortest_distance_1 = -1
    index_1 = -1
    for i in range(0, len(path)):
        point = path[i]
        distance = haversine_distance(point[0], point[1], stop_1["location"]["lat"], stop_1["location"]["lng"])
        if shortest_distance_1 < 0 or distance < shortest_distance_1:
            shortest_distance_1 = distance
            index_1 = i
    shortest_distance_2 = -1
    index_2 = -1
    for i in range(index_1, len(path)):
        point = path[i]
        distance = haversine_distance(point[0], point[1], stop_2["location"]["lat"], stop_2["location"]["lng"])
        if shortest_distance_2 < 0 or distance < shortest_distance_2:
            shortest_distance_2 = distance
            index_2 = i
    section = []
    for i in range(index_1, index_2 + 1):
        section.append(path[i])
    return section, shortest_distance_1 + shortest_distance_2


def find_trim_closest_sections(paths, stop_1, stop_2):
    shortest_distance = -1
    result = None
    for path in paths:
        section, distance = find_trim_closest_section(path, stop_1, stop_2)
        if len(section) > 1 and (shortest_distance < 0 or distance < shortest_distance):
            result = section
    return result


def resolve_write_ctb_paths(data):
    for route_number, route_data in data.items():
        print(route_number)
        result = {}
        for bound, bound_data in route_data.items():
            result[bound] = {}
            stop_pairs = get_all_ctb_stop_pairs(route_number, bound)
            for stop_pair in stop_pairs:
                str_parts = stop_pair.split("+")
                stop_1 = data_sheet["stopList"][str_parts[0]]
                stop_2 = data_sheet["stopList"][str_parts[1]]
                positions_list = []
                for variant, positions in bound_data.items():
                    positions_list.append(positions)
                section = find_trim_closest_sections(positions_list, stop_1, stop_2)
                if section is not None:
                    result[bound][stop_pair] = section
        write_dict_to_file("data/route_paths_ctb\\" + route_number + ".json", result)


def convert_weekday_ranges(input_string):
    numbers = sorted(map(int, input_string))
    ranges = []
    start = end = numbers[0]
    for i in range(1, len(numbers)):
        if numbers[i] == end + 1:
            end = numbers[i]
        else:
            if start == end:
                ranges.append(str(start))
            elif start + 1 == end:
                ranges.append(f"{start},{end}")
            else:
                ranges.append(f"{start}-{end}")
            start = end = numbers[i]
    if start == end:
        ranges.append(str(start))
    elif start + 1 == end:
        ranges.append(f"{start},{end}")
    else:
        ranges.append(f"{start}-{end}")
    return ",".join(ranges)


def merge_gmb_timetable(timetable):
    merged_timetable = {}
    for i in range(1, 8):
        weekday = str(i)
        if weekday in timetable:
            merged_weekday = weekday
            entry = timetable[weekday]
            for u in range(i + 1, 8):
                weekday_compare = str(u)
                if weekday_compare in timetable:
                    entry_compare = timetable[weekday_compare]
                    if entry == entry_compare:
                        del timetable[weekday_compare]
                        merged_weekday += weekday_compare
            merged_timetable[merged_weekday] = entry
    for weekday, entry in merged_timetable.items():
        ranges = convert_weekday_ranges(weekday)
        if ranges == "1-7":
            zh = "每天"
            en = "Daily"
        else:
            zh = "星期" + ranges.replace(",", "、").replace("-", "至")
            for key, value in weekday_map_zh.items():
                zh = zh.replace(key, value)
            en = ranges.replace(",", ", ").replace("-", " to ")
            for key, value in weekday_map_en.items():
                en = en.replace(key, value)
        entries = []
        for a, b in entry.items():
            entries.append({"period": a, "frequency": b})
        merged_timetable[weekday] = {"weekday_zh": zh, "weekday_en": en, "entries": entries}
    final_timetable = []
    for a, b in merged_timetable.items():
        final_timetable.append({"weekday": a, "weekday_zh": b["weekday_zh"], "weekday_en": b["weekday_en"], "times": b["entries"]})
        del b["weekday_zh"]
        del b["weekday_en"]
    return final_timetable


def write_gmb_data():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        futures = []
        for region, route_list in gmb_route_list.items():
            for route_number in route_list:
                futures.append(executor.submit(write_gmb_data_0, region=region, route_number=route_number))
        for future in concurrent.futures.as_completed(futures):
            pass


def write_gmb_data_0(region, route_number):
    try:
        print(region + " > " + route_number)
        data = get_json(gmb_route_data_url.replace("{region}", region).replace("{route}", route_number))["data"]
        for entry in data:
            gtfs_id = str(entry["route_id"])
            result = {"route": route_number, "region": region, "gtfsId": gtfs_id, "bound": {}}
            for direction_entry in entry["directions"]:
                bound = "O" if direction_entry["route_seq"] == 1 else "I"
                timetable = {}
                for timetable_entry in direction_entry["headways"]:
                    for i in range(0, 7):
                        weekday = str(i + 1)
                        if timetable_entry["weekdays"][i]:
                            start_time = timetable_entry["start_time"][:5]
                            end_time = timetable_entry["end_time"][:5]
                            if start_time == end_time:
                                times = start_time
                                frequency = ""
                            else:
                                times = start_time + "-" + end_time
                                frequency = str(timetable_entry["frequency"])
                                if timetable_entry["frequency_upper"] is not None and timetable_entry["frequency"] != timetable_entry["frequency_upper"]:
                                    frequency += "-" + str(timetable_entry["frequency_upper"])
                            if weekday not in timetable:
                                timetable[weekday] = {}
                            timetable[weekday][times] = frequency
                result["bound"][bound] = {"timetable": merge_gmb_timetable(timetable)}
            write_dict_to_file("data/route_data_gmb\\" + gtfs_id + ".json", result)
    except Exception as e:
        print(e)
        print(traceback.format_exc())


def write_mtr_bus_timetable():
    route_entries = [[y[1:len(y) - 1] if y.startswith("\"") else y for y in x.split(",")] for x in mtr_bus_route_list.splitlines()[1:]]
    for route_entry in route_entries:
        route_number = route_entry[0]
        print(route_number)
        result = {"route": route_number, "bound": {}}
        data = json.loads(re.search("populateSearchDetailResult_chi\((.*)\);", get_text(mtr_bus_info_url.replace("{route}", route_number), False))[1])[0]
        for each in ["busServiceTime", "busServiceTimeSecond"]:
            if each in data and data[each] is not None:
                for service_time in data[each]:
                    periods = service_time["firstLastTime"].split("<br>")
                    for i in range(0, len(periods)):
                        period = periods[i]
                        periods[i] = re.sub("(?<![0-9])[0-9]:[0-9]{2}", lambda match: "0" + match[0], period)
                    frequencies = service_time["frequency"].replace("~", "-").split("<br>")
                    bound = "O" if service_time["direction"] == "1" else "I"
                    day_frame_type = service_time["dayFrameType"]
                    weekday = ""
                    if day_frame_type == 1:
                        weekday = "12345"
                    elif day_frame_type == 2:
                        weekday = "123456"
                    elif day_frame_type == 3:
                        weekday = "6"
                    elif day_frame_type == 4:
                        weekday = "7"
                    ranges = convert_weekday_ranges(weekday)
                    if ranges == "1-7":
                        zh = "每天"
                        en = "Daily"
                    else:
                        zh = "星期" + ranges.replace(",", "、").replace("-", "至")
                        for key, value in weekday_map_zh.items():
                            zh = zh.replace(key, value)
                        en = ranges.replace(",", ", ").replace("-", " to ")
                        for key, value in weekday_map_en.items():
                            en = en.replace(key, value)
                    if bound not in result["bound"]:
                        result["bound"][bound] = {"timetable": []}
                    times = []
                    for i in range(0, len(periods)):
                        times.append({"period": periods[i], "frequency": frequencies[i]})
                    result["bound"][bound]["timetable"].append({"weekday": weekday, "weekday_zh": zh, "weekday_en": en, "times": times})
        write_dict_to_file("data/route_data_mtr_bus\\" + route_number + ".json", result)


def write_nlb_timetable():
    for route_entry in nlb_route_list:
        route_id = route_entry["routeId"]
        print(route_id)
        result = {"id": route_id, "route": route_entry["routeNo"], "timetable": []}
        html_text = "".join(get_text(nlb_info_url.replace("{id}", route_id), False).splitlines())
        if "本路線只於指定日子提供服務" in html_text:
            pass
        elif re.search("(星期.*?)</tbody></table>", html_text):
            for match in re.finditer("(星期.*?)</tbody></table>", html_text):
                if re.search("(星期.*)</p>", match[1]):
                    weekday_str = re.search("(星期.*)</p>", match[1])[1]
                    school_holiday = "(學校假期除外)" not in weekday_str and "(學校假期及公眾假期除外)" not in weekday_str
                    school_day_only = "(只於上課日服務)" in weekday_str
                    no_school_day = "(上學日除外)" in weekday_str
                    public_holiday = "(公眾假期除外)" not in weekday_str and "(星期日及公眾假期除外)" not in weekday_str and "(學校假期及公眾假期除外)" not in weekday_str
                    weekday_str = weekday_str.replace("(上學日除外)", "").replace("(學校假期除外)", "").replace("(只於上課日服務)", "").replace("(公眾假期除外)", "").replace("(星期日及公眾假期除外)", "").replace("(學校假期及公眾假期除外)", "").replace("星期", "").strip()
                    if weekday_str == "一至五":
                        weekday = "12345"
                    elif weekday_str == "一至六":
                        weekday = "123456"
                    elif weekday_str == "六":
                        weekday = "6"
                    elif weekday_str == "六、日及公眾假期":
                        weekday = "67"
                    elif weekday_str == "日及公眾假期":
                        weekday = "7"
                    else:
                        raise Exception("What is weekday " + weekday_str)
                    periods = []
                    frequencies = []
                    for period_match in re.finditer("([0-9]{2}:[0-9]{2} ?- ?[0-9]{2}:[0-9]{2}).*?</td>.*?<td>([0-9]+(?: ?- ?[0-9]+)?)</td>", match[1]):
                        periods.append(period_match[1])
                        frequencies.append(period_match[2])
                    if len(periods) <= 0:
                        single = []
                        matches = re.findall("([0-9]{2}:[0-9]{2})", match[1])
                        if len(matches) < 3:
                            for i in range(0, len(matches)):
                                single.append(matches[i])
                        else:
                            h1, m1 = (int(x) for x in matches[1].split(":"))
                            h2, m2 = (int(x) for x in matches[2].split(":"))
                            if h1 > h2 or (h1 == h2 and m1 > m2):
                                for i in range(0, len(matches), 2):
                                    single.append(matches[i])
                                for i in range(1, len(matches), 2):
                                    single.append(matches[i])
                            else:
                                for i in range(0, len(matches)):
                                    single.append(matches[i])
                        periods.append(", ".join(single))
                        frequencies.append("")
                    ranges = convert_weekday_ranges(weekday)
                    if ranges == "1-7":
                        zh = "每天"
                        en = "Daily"
                    else:
                        zh = "星期" + ranges.replace(",", "、").replace("-", "至")
                        for key, value in weekday_map_zh.items():
                            zh = zh.replace(key, value)
                        en = ranges.replace(",", ", ").replace("-", " to ")
                        for key, value in weekday_map_en.items():
                            en = en.replace(key, value)
                    if not public_holiday and not school_holiday:
                        zh += " (學校假期及公眾假期除外)"
                        en += " (Except School & Public Holidays)"
                    elif not public_holiday:
                        zh += " (公眾假期除外)"
                        en += " (Except Public Holidays)"
                    elif not school_holiday:
                        zh += " (學校假期除外)"
                        en += " (Except School Holidays)"
                    elif school_day_only:
                        zh += " (只於上課日服務)"
                        en += " (School Days Only)"
                    elif no_school_day:
                        zh += " (上學日除外)"
                        en += " (Except School Days)"
                    times = []
                    for i in range(0, len(periods)):
                        times.append({"period": periods[i], "frequency": frequencies[i], "school_holiday": school_holiday, "school_day_only": school_day_only, "public_holiday": public_holiday, "no_school_day": no_school_day})
                    result["timetable"].append({"weekday": weekday, "weekday_zh": zh, "weekday_en": en, "times": times})
        write_dict_to_file("data/route_data_nlb\\" + route_id + ".json", result)


def write_dict_to_file(file, dictionary, indent=4):
    json_object = json.dumps(dictionary, indent=indent)
    os.makedirs(os.path.dirname(file), exist_ok=True)
    with open(file, "w") as outfile:
        outfile.write(json_object)


if __name__ == '__main__':
    print("Initializing data...")
    weekday_map_zh = {'1': '一', '2': '二', '3': '三', '4': '四', '5': '五', '6': '六', '7': '日及公眾假期'}
    weekday_map_en = {'1': 'Monday', '2': 'Tuesday', '3': 'Wednesday', '4': 'Thursday', '5': 'Friday', '6': 'Saturday', '7': 'Sunday & Public Holidays'}
    data_sheet = get_json("https://raw.githubusercontent.com/hkbus/hk-bus-crawling/gh-pages/routeFareList.json")
    paths_url = "https://m4.kmb.hk:8012/api/rt/{route}/{bound}/{type}/?apikey=com.mobilesoft.2015"
    kmb_route_list = get_json("https://data.etabus.gov.hk/v1/transport/kmb/route/")["data"]
    ctb_route_list = get_json("https://rt.data.gov.hk/v2/transport/citybus/route/ctb")
    ctb_bbi_tc_url = "https://www.citybus.com.hk/concessionApi/public/bbi/api/v1/scheme/tc/"
    ctb_bbi_en_url = "https://www.citybus.com.hk/concessionApi/public/bbi/api/v1/scheme/en/"
    ctb_path_url = "https://mobile.citybus.com.hk/nwp3/getline.php?info="
    mtr_bus_route_list = get_text("https://opendata.mtr.com.hk/data/mtr_bus_routes.csv")
    mtr_bus_stop_list = get_text("https://opendata.mtr.com.hk/data/mtr_bus_stops.csv")
    mtr_bus_fare_list = get_text("https://opendata.mtr.com.hk/data/mtr_bus_fares.csv")
    mtr_bus_info_url = "https://www.mtr.com.hk/ch/customer/services/searchBusRouteDetails.php?routeID={route}"
    gmb_route_list = get_json("https://data.etagmb.gov.hk/route/")["data"]["routes"]
    gmb_route_data_url = "https://data.etagmb.gov.hk/route/{region}/{route}"
    nlb_route_list = get_json("https://rt.data.gov.hk/v2/transport/nlb/route.php?action=list")["routes"]
    nlb_info_url = "https://www.nlb.com.hk/route/detail/{id}"

    print("Resolving KMB BBI...")
    bbi_data_f1 = get_json("https://www.kmb.hk/storage/BBI_routeF1.js")
    write_dict_to_file("data/bbi_f1.json", resolve_bbi_data(bbi_data_f1))
    bbi_data_b1 = get_json("https://www.kmb.hk/storage/BBI_routeB1.js")
    write_dict_to_file("data/bbi_b1.json", resolve_bbi_data(bbi_data_b1))

    print("Resolving KMB Regional Two Way Section Fare...")
    a = resolve_regional_two_way_section_fare(get_text("https://www.kmb.hk/storage/scheme_shortdistance.html"))
    write_dict_to_file("data/regional_two_way_section_fare.json", a)

    print("Resolving CTB BBI...")
    read_ctb_bbi()

    print("Resolving MTR Bus Route Data...")
    resolve_mtr_bus_data()

    #data = get_json("file:///data/kmb_gmb_interchange.json")
    #while True:
    #    input_text = input()
    #    print("GMB " + input_text)
    #    if input_text == "done":
    #        break
    #    region = input()
    #    print("Region " + region)
    #    gmb_routes = [x.strip() for x in input_text.split(",")]
    #    input_text = input()
    #    print("KMB " + input_text)
    #    kmb_routes = [x.strip() for x in input_text.split(",")]
    #    for gmb in gmb_routes:
    #        entry = []
    #        for kmb in kmb_routes:
    #            entry.append({
    #                "route": kmb,
    #                "bound": "O"
    #            })
    #            entry.append({
    #                "route": kmb,
    #                "bound": "I"
    #            })
    #        gmb_ex_data = get_json("https://data.etagmb.gov.hk/route/" + region + "/" + gmb)["data"]
    #        if len(gmb_ex_data) > 0:
    #            gmb_id = str(gmb_ex_data[0]["route_id"])
    #            data["gmb"][gmb_id + "_O"] = entry
    #            data["gmb"][gmb_id + "_I"] = entry
    #    print("Added")
    #
    #write_dict_to_file("data/kmb_gmb_interchange_1.json", data)

    #data = get_json("file:///data/kmb_gmb_interchange.json")
    #inverted_data = {}
    #for key, value in data['gmb'].items():
    #    for item in value:
    #        route_key = item['route']
    #        bound_value = item['bound']
    #        if route_key not in inverted_data:
    #            inverted_data[route_key] = {}
    #        if bound_value not in inverted_data[route_key]:
    #            inverted_data[route_key][bound_value] = []
    #        inverted_data[route_key][bound_value].append(key)
    #data["kmb"] = inverted_data
    #
    #write_dict_to_file("data/kmb_gmb_interchange_1.json", data)

    #raw_path = get_ctb_paths(get_json("file:///data/ctb_timeable_macro\\ctb_route_ids_test.json"))
    #resolve_write_ctb_paths(raw_path)

    print("Resolving GMB Route Data...")
    write_gmb_data()

    print("Resolving MTR Bus Timetables...")
    write_mtr_bus_timetable()

    print("Resolving NLB Timetables...")
    write_nlb_timetable()

    print("Writing KMB Route Paths...")
    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        route_numbers = get_all_routes()
        route_data = get_all_routes_data()
        for route_number in route_numbers:
            futures.append(executor.submit(add_route_path, route_number=route_number, route_data=route_data))
        concurrent.futures.wait(futures, timeout=1800, return_when=concurrent.futures.ALL_COMPLETED)
    #add_route_path("A47X", get_all_routes_data())

