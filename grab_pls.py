#!/usr/bin/env python3
"""
RadioGarden — это веб-сервис, который позволяет пользователям слушать радиостанции со всего мира. Основной элемент
интерфейса — виртуальный глобус, на котором можно выбирать страны и города для прослушивания локальных радиостанций.
Это интерактивный и уникальный способ исследовать радиокультуру разных стран.
"""
import math
import random
import sys
from typing import Final, List, Dict

import xml.etree.ElementTree as ET
import uuid
import requests

V = ""
PLACES: Final[str] = "https://radio.garden/api/ara/content/places"
CONTENT_PAGE: Final[str] = "https://radio.garden/api/ara/content/page"
CONTENT_LISTEN: Final[str] = "https://radio.garden/api/ara/content/listen"

F_: Final[str] = "./Radio Garden.xspf"


def deg2num(lat_deg, lon_deg, zoom):
    """
    Конвертирует географические координаты в координаты тайлов.

    :param lat_deg: Широта в градусах.
    :param lon_deg: Долгота в градусах.
    :param zoom: Уровень масштаба (zoom level).
    :return: Координаты тайлов (x, y).
    """
    lat_rad = math.radians(lat_deg)
    n = 2.0**zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)

    return zoom, xtile, ytile


class Xspf:
    def __init__(self, title="Playlist"):

        self.total_elements = 0
        self.current_proccess = 0

        self.playlist = ET.Element("playlist", xmlns="http://xspf.org/ns/0/", version="1")
        self.title = title
        ET.register_namespace("aimp", "http://www.aimp.ru/playlist/ns/0/")

        # Добавление Summary Entry сразу перед создания плейлиста
        summary = ET.SubElement(self.playlist, "extension", application="http://www.aimp.ru/playlist/summary/0")
        ET.SubElement(summary, "{http://www.aimp.ru/playlist/ns/0/}prop", name="ID").text = str(uuid.uuid4())
        ET.SubElement(summary, "{http://www.aimp.ru/playlist/ns/0/}prop", name="Name").text = self.title
        ET.SubElement(summary, "{http://www.aimp.ru/playlist/ns/0/}prop", name="NameIsAutoSet").text = "0"
        ET.SubElement(summary, "{http://www.aimp.ru/playlist/ns/0/}prop", name="Shuffled").text = "0"
        ET.SubElement(summary, "{http://www.aimp.ru/playlist/ns/0/}prop", name="UserReordered").text = "0"
        ET.SubElement(summary, "{http://www.aimp.ru/playlist/ns/0/}prop", name="SortingTemplate").text = (
            "%Artist %Year %Album"
        )

        settings = ET.SubElement(self.playlist, "extension", application="http://www.aimp.ru/playlist/settings/0")
        ET.SubElement(settings, "{http://www.aimp.ru/playlist/ns/0/}prop", name="Flags").text = str(554)
        ET.SubElement(settings, "{http://www.aimp.ru/playlist/ns/0/}prop", name="FormatMainLine").text = "%Title"
        ET.SubElement(settings, "{http://www.aimp.ru/playlist/ns/0/}prop", name="FormatSecondLine").text = (
            "%Artist - %Album"
        )
        ET.SubElement(settings, "{http://www.aimp.ru/playlist/ns/0/}prop", name="GroupFormatLine").text = "GRP_TITLE"
        ET.SubElement(settings, "{http://www.aimp.ru/playlist/ns/0/}prop", name="GroupFormatLine").text = (
            "%Artist %Album"
        )

        self.tracklist = ET.SubElement(self.playlist, "trackList")

    def add_track(self, location, title, country, city, geo):
        track = ET.SubElement(self.tracklist, "track")
        ET.SubElement(track, "location").text = location
        ET.SubElement(track, "title").text = title
        ET.SubElement(track, "creator").text = country
        ET.SubElement(track, "album").text = city
        ## ====

        style = "light_all"
        zoom = 8
        z, x, y = deg2num(geo[1], geo[0], zoom)
        sub_dmn = random.choice("abcd")
        img_url = f"https://{sub_dmn}.basemaps.cartocdn.com/{style}/{z}/{x}/{y}.png"
        ET.SubElement(track, "image").text = img_url

    def __str__(self):
        return ET.tostring(self.playlist, encoding="unicode")

    def save(self, filename):
        tree = ET.ElementTree(self.playlist)
        tree.write(filename, encoding="utf-8", xml_declaration=True)

    # ================================================
    def fill(self):

        info("Получение списка зон...\n")
        response = requests.get(PLACES, timeout=30)
        response.raise_for_status()  # Проверка на ошибки HTTP
        data = response.json()
        info("Получено:\n")

        countries: Dict[str, List[str]] = {}
        zones = data["data"]["list"]
        info(f"  зон = {len(zones)}\n")
        for zone in zones:
            country_name = zone["country"]
            if country_name in countries:
                countries[country_name].append((zone["id"], zone["geo"]))
            else:
                countries[country_name] = [(zone["id"], zone["geo"])]

        self.total_elements = sum(len(subarray) for subarray in countries)

        for country_name, cities in countries.items():
            # info(f'\nОбработка, страна "{country_name}" ({len(cities)} запись/и) ...\n')
            self._fetch_cities(country_name, cities)

    def _fetch_cities(self, country_name, cities):

        for id_, geo in cities:

            # info(f"\n  {id_}\n")
            response = requests.get(f"{CONTENT_PAGE}/{id_}/channels", timeout=30)
            response.raise_for_status()  # Проверка на ошибки HTTP
            data = response.json()
            city_name = data["data"]["title"]
            self.current_proccess = self.current_proccess + 1
            remaining = self.total_elements - self.current_proccess
            info(f"\n  (remaining: {remaining}) * current: {city_name}\n")
            self._fetch_stations(country_name, city_name, geo, data)

    def _fetch_stations(self, country_name, city_name, geo, data):
        if "content" in data["data"]:  # Проверяем наличие ключа 'content' в данных
            info(f"    {country_name}, {city_name} {geo}\n")
            for content in data["data"]["content"]:  # Перебираем каждый элемент в 'content'

                if "items" in content:  # Проверяем наличие ключа 'items'
                    for n, item in enumerate(content["items"], start=1):  # Перебираем каждый элемент в 'items'
                        if "page" in item:  # Проверяем наличие 'title' и 'href'
                            page = item["page"]
                            station_title = page["title"]
                            stream_id = page["url"].split("/")[-1]
                            url = f"{CONTENT_LISTEN}/{stream_id}/channel.mp3?r=1&1715617284592"
                            info(f"    - {n}) {station_title}; {{ {stream_id}; ")
                            station_stream_url = get_redirect_url(url)
                            info(f"{station_stream_url} }}\n")

                            self.add_track(station_stream_url, station_title, country_name, city_name, geo)


def info(str_):
    print(str_, end="", file=sys.stderr)


def get_redirect_url(url):
    """
    Attempts to connect to the given URL and captures the redirect URL without following it.

    Args:
    url (str): The initial URL to connect.

    Returns:
    str: The URL to which a redirect was attempted, or None if there was no redirect.
    """
    response = requests.get(url, allow_redirects=False, timeout=30)  # Выполняем запрос, не следуя перенаправлениям
    if 300 <= response.status_code < 400:
        # Проверяем, есть ли в ответе заголовок 'Location', который указывает на URL для перенаправления
        return response.headers.get("Location")
    else:
        raise ValueError


if __name__ == "__main__":
    pass
    TITLE = "Radio Garden"
    xspf = Xspf(TITLE)
    xspf.fill()
    xspf.save(f"{TITLE}.xspf")
