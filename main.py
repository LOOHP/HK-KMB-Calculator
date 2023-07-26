import concurrent.futures
import math
import zlib
from urllib.request import urlopen, Request
import json
import re
import chardet


def get_json(url):
    response = urlopen(url)
    return json.loads(response.read())


def get_text(url):
    req = Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.93 Safari/537.36')
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
    for i in range(1, len(locations)):
        loc = locations[i]
        distance = haversine_distance(location[0], location[1], loc[0], loc[1])
        if distance <= closest_distance:
            closest_distance = distance
        else:
            return i - 1
    return len(locations) - 1


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


def sort_sections(start, sections):
    pool = list(sections)
    result = []
    location = start
    while len(pool) > 0:
        closest = find_closest_section(location, pool)
        pool.remove(closest)
        result.append(closest)
        location = closest[0]
    return result


def kmb_route_exists(route):
    for kmb_route in kmb_route_list:
        if (route["route"] == kmb_route["route"] and route["bound"]["kmb"] == kmb_route["bound"] and route["serviceType"] == kmb_route["service_type"] and route["orig"]["zh"] == kmb_route["orig_tc"] and route["dest"]["zh"] == kmb_route["dest_tc"]):
            return True
    return False


def resolve_route_information(data, start, stops):
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
    sorted_result = sort_sections(start, result)
    combined = []
    for section in sorted_result:
        combined = section + combined
    combined.reverse()
    if len(stops) <= 1:
        return combined
    result = []
    for i in range(1, len(stops) - 1):
        stop = data_sheet["stopList"][stops[i]]
        location = [stop["location"]["lat"], stop["location"]["lng"]]
        index = find_first_closest_location_index(location, combined)
        result.append(combined[:(index + 1)])
        del combined[0:(index + 1)]
    result.append(combined)
    return result


def add_route_path(route_number, route_data):
    print(route_number)
    route_paths = {}
    for entry in route_data:
        if entry["route"] == route_number:
            first_stop = get_json("https://data.etabus.gov.hk/v1/transport/kmb/route-stop/" + route_number + "/" + ("outbound" if entry["bound"] == "O" else "inbound") + "/" + entry["service_type"])["data"][0]["stop"]
            first_stop_data = get_json("https://data.etabus.gov.hk/v1/transport/kmb/stop/" + first_stop)["data"]
            stops = None
            for key, route in data_sheet["routeList"].items():
                if "kmb" in route["bound"] and kmb_route_exists(route) and route["route"] == route_number and entry["bound"] == route["bound"]["kmb"] and entry["service_type"] == route["serviceType"]:
                    stops = route["stops"]["kmb"]
                    break
            try:
                b = resolve_route_information(get_text(paths_url.replace("{route}", route_number).replace("{bound}", "1" if entry["bound"] == "O" else "2").replace(
                    "{type}", entry["service_type"])), [float(first_stop_data["lat"]), float(first_stop_data["long"])], stops)
                if entry["bound"] not in route_paths:
                    route_paths[entry["bound"]] = {}
                route_paths[entry["bound"]][entry["service_type"]] = b
            except:
                pass
    write_dict_to_file("C:\\Users\\LOOHP\\Desktop\\temp\\HK Bus Fare\\route_paths\\" + route_number + ".json", route_paths)


def write_dict_to_file(file, dictionary, indent=4):
    json_object = json.dumps(dictionary, indent=indent)

    with open(file, "w") as outfile:
        outfile.write(json_object)


if __name__ == '__main__':
    data_sheet = get_json("https://raw.githubusercontent.com/hkbus/hk-bus-crawling/gh-pages/routeFareList.json")
    paths_url = "https://m4.kmb.hk:8012/api/rt/{route}/{bound}/{type}/?apikey=com.mobilesoft.2015"
    kmb_route_list = get_json("https://data.etabus.gov.hk/v1/transport/kmb/route/")

    #bbi_data_f1 = get_json("https://www.kmb.hk/storage/BBI_routeF1.js")
    #write_dict_to_file("C:\\Users\\LOOHP\\Desktop\\temp\\HK Bus Fare\\bbi_f1.json", resolve_bbi_data(bbi_data_f1))
    #bbi_data_b1 = get_json("https://www.kmb.hk/storage/BBI_routeB1.js")
    #write_dict_to_file("C:\\Users\\LOOHP\\Desktop\\temp\\HK Bus Fare\\bbi_b1.json", resolve_bbi_data(bbi_data_b1))

    #print(get_text("https://search.kmb.hk/KMBWebSite/AnnouncementPicture.ashx?url=1686913282.html"))

    #a = resolve_regional_two_way_section_fare(get_text("https://www.kmb.hk/storage/scheme_shortdistance.html"))
    #write_dict_to_file("C:\\Users\\LOOHP\\Desktop\\temp\\HK Bus Fare\\regional_two_way_section_fare.json", a)

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = []
        route_numbers = get_all_routes()
        route_data = get_all_routes_data()
        for route_number in route_numbers:
            futures.append(executor.submit(add_route_path, route_number=route_number, route_data=route_data))
        for future in concurrent.futures.as_completed(futures):
            pass
