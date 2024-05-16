#!/usr/bin/env python3
"""
RadioGarden — это веб-сервис, который позволяет пользователям слушать радиостанции со всего мира. Основной элемент
интерфейса — виртуальный глобус, на котором можно выбирать страны и города для прослушивания локальных радиостанций.
Это интерактивный и уникальный способ исследовать радиокультуру разных стран.
"""
import json
import math
import random
import sys
from typing import Final, List, Dict

import xml.etree.ElementTree as ET
import uuid
import requests
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console


V = ""
PLACES: Final[str] = "https://radio.garden/api/ara/content/places"
CONTENT_PAGE: Final[str] = "https://radio.garden/api/ara/content/page"
CONTENT_LISTEN: Final[str] = "https://radio.garden/api/ara/content/listen"

CONSOLE = Console()

F_: Final[str] = "./Radio Garden.xspf"

CACHE_FILE: Final[str]  # Определение переменной для пути к файлу кэша


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

        # Добавление Summary Entry сразу перед созданием плейлиста
        summary = ET.SubElement(self.playlist, "extension", application="http://www.aimp.ru/playlist/summary/0")
        ET.SubElement(summary, "{http://www.aimп.ru/playlist/ns/0/}prop", name="ID").text = str(uuid.uuid4())
        ET.SubElement(summary, "{http://www.aimп.ru/playlist/ns/0/}prop", name="Name").text = self.title
        ET.SubElement(summary, "{http://www.aimп.ru/playlist/ns/0/}prop", name="NameIsAutoSet").text = "0"
        ET.SubElement(summary, "{http://www.aimп.ru/playlist/ns/0/}prop", name="Shuffled").text = "0"
        ET.SubElement(summary, "{http://www.aimп.ru/playlist/ns/0/}prop", name="UserReordered").text = "0"
        ET.SubElement(summary, "{http://www.aimп.ru/playlist/ns/0/}prop", name="SortingTemplate").text = (
            "%Artist %Year %Album"
        )

        settings = ET.SubElement(self.playlist, "extension", application="http://www.aimп.ru/playlist/settings/0")
        ET.SubElement(settings, "{http://www.aimп.ru/playlist/ns/0/}prop", name="Flags").text = str(554)
        ET.SubElement(settings, "{http://www.aimп.ru/playlist/ns/0/}prop", name="FormatMainLine").text = "%Title"
        ET.SubElement(settings, "{http://www.aimп.ru/playlist/ns/0/}prop", name="FormatSecondLine").text = (
            "%Artist - %Album"
        )
        ET.SubElement(settings, "{http://www.aimп.ru/playlist/ns/0/}prop", name="GroupFormatLine").text = "GRP_TITLE"
        ET.SubElement(settings, "{http://www.aimп.ru/playlist/ns/0/}prop", name="GroupFormatLine").text = (
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
        zoom = 6
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
    def fill(self, progress):

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

        self.total_elements = sum(len(cities) for cities in countries.values())
        task = progress.add_task("[cyan]Обработка зон...", total=self.total_elements)
        progress.update(task, total=self.total_elements)

        for country_name, cities in countries.items():
            self._fetch_cities(country_name, cities, progress, task)

    def _fetch_cities(self, country_name, cities, progress, task):
        for id_, geo in cities:
            response = requests.get(f"{CONTENT_PAGE}/{id_}/channels", timeout=30)
            response.raise_for_status()  # Проверка на ошибки HTTP
            data = response.json()
            city_name = data["data"]["title"]
            self.current_proccess += 1
            remaining = self.total_elements - self.current_proccess
            info(f"\n  (remaining: {remaining}) * current: {city_name}\n")
            progress.update(
                task,
                advance=1,
                description=f"{str(self.current_proccess).ljust(len(str(self.total_elements)))} из {self.total_elements}",
            )
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


CACHE_FILE: Final[str]


def load_cache():
    """
    Загружает кэшированные данные из файла.

    :param cache_file: Путь к файлу с кэшированными данными.
    :return: Кэшированные данные или пустой словарь, если файл не существует.
    """
    global CACHE_FILE

    response = requests.get(PLACES, timeout=30)
    response.raise_for_status()  # Проверка на ошибки HTTP
    data = response.json()

    if not data["version"]:
        raise ValueError
    CACHE_FILE = f'{data["version"]}.cache'

    try:
        with open(CACHE_FILE, "r") as file:
            return json.load(file)
    except FileNotFoundError:
        return {}


cache_streams = load_cache()


def save_cache(cache):
    """
    Сохраняет данные в файл для кэширования.

    :param cache: Данные для сохранения.
    :param cache_file: Путь к файлу кэша.
    """
    with open(CACHE_FILE, "w") as file:
        json.dump(cache, file)


def get_redirect_url(url):
    """
    Attempts to connect to the given URL and captures the redirect URL without following it.

    Args:
    url (str): The initial URL to connect.
    cache (dict): Кэшированные данные.

    Returns:
    str: The URL to which a redirect was attempted, or None if there was no redirect.
    """

    if url in cache_streams:
        return cache_streams[url]

    response = requests.get(url, allow_redirects=False, timeout=30)  # Выполняем запрос, не следуя перенаправлениям
    if 300 <= response.status_code < 400:
        redirect_url = response.headers.get("Location")
        if redirect_url:
            cache_streams[url] = redirect_url
            save_cache(cache_streams)
        return redirect_url
    else:
        raise ValueError("No redirect or unexpected response")


if __name__ == "__main__":

    title = "Radio Garden"
    xspf = Xspf(title)

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
    ) as progress:
        xspf.fill(progress)
    xspf.save(f"{title}.xspf")
