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
from typing import Final, List, Dict, Tuple

import xml.etree.ElementTree as ET
import uuid
import requests
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.console import Console
import os


V = ""
PLACES: Final[str] = "https://radio.garden/api/ara/content/places"
CONTENT_PAGE: Final[str] = "https://radio.garden/api/ara/content/page"
CONTENT_LISTEN: Final[str] = "https://radio.garden/api/ara/content/listen"

CONSOLE = Console()

F_: Final[str] = "./Radio Garden.xspf"


CACHE_DIR: Final[str] = "cache"
os.makedirs(CACHE_DIR, exist_ok=True)


class Map:

    TILE_SIZE = 256

    @staticmethod
    def deg2num(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int, int]:
        """
        конвертирует географические координаты (широта и долгота в градусах) в координаты тайлов на карте на
        заданном уровне масштаба (zoom). Он возвращает кортеж (zoom, xtile, ytile), где xtile и ytile — это
        координаты тайла, который содержит указанную точку.

        :param lat_deg: Широта в градусах.
        :param lon_deg: Долгота в градусах.
        :param zoom: Уровень масштаба (zoom level).
        """

        lat_rad = math.radians(lat_deg)
        n = 2.0**zoom
        xtile = int((lon_deg + 180.0) / 360.0 * n)
        ytile = int((1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n)

        return zoom, xtile, ytile

    @staticmethod
    def deg2tile(lat_deg: float, lon_deg: float, zoom: int) -> Tuple[int, int, int, float, float]:
        """
        Похож на deg2num, но дополнительно возвращает пиксельные координаты внутри тайла (pixel_x, pixel_y).
        Эти значения показывают, где внутри тайла находится указанная точка, что позволяет понять, насколько точно
        она центрирована.
        """

        lat_rad = math.radians(lat_deg)
        n = 2.0**zoom
        xtile_f = (lon_deg + 180.0) / 360.0 * n
        ytile_f = (1.0 - math.log(math.tan(lat_rad) + (1 / math.cos(lat_rad))) / math.pi) / 2.0 * n
        xtile = int(xtile_f)
        ytile = int(ytile_f)
        xpixel = (xtile_f - xtile) * Map.TILE_SIZE  # 256 - размер тайла в пикселях
        ypixel = (ytile_f - ytile) * Map.TILE_SIZE
        return zoom, xtile, ytile, xpixel, ypixel

    @staticmethod
    def find_best_tile(lat_deg: float, lon_deg: float) -> Tuple[int, int, int]:
        """определяет уровень масштаба, при котором точка находится ближе всего к центру тайла. Функция
        find_best_zoom вычисляет расстояние от точки до центра тайла (128, 128) на каждом уровне масштаба и
        возвращает zoom уровень с минимальным расстоянием. Это позволит вам определить, на каком уровне масштаба
        точка будет максимально центрирована в тайле."""

        best_tile = None
        min_distance = float("inf")

        for zoom in range(6, 12, 1):  # Перебор уровней масштаба от 3 до 18 с шагом 3
            _, xtile, ytile, pixel_x, pixel_y = Map.deg2tile(lat_deg, lon_deg, zoom)
            # Расчет расстояния от точки до центра тайла
            distance = math.sqrt(
                (pixel_x - (Map.TILE_SIZE / 2)) ** 2 + (pixel_y - (Map.TILE_SIZE / 2)) ** 2
            )  # 128 - центр тайла для 256x256
            if distance < min_distance:
                min_distance = distance
                best_tile = (zoom, xtile, ytile)

        if not best_tile:
            raise ValueError
        return best_tile


class Xspf:
    def __init__(self, title="Playlist"):

        self.total_elements = 0
        self.current_proccess = 0

        self.rg_version = ""
        response = requests.get(PLACES, timeout=30)
        response.raise_for_status()  # Проверка на ошибки HTTP
        data = response.json()

        if not data["version"]:
            raise ValueError
        self.rg_version = data["version"]

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

        z, x, y = Map.find_best_tile(geo[1], geo[0])
        img_url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
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

        countries = {}
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
            data = self._fetch_json(id_)
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
                            station_stream_url = self._get_redirect_url(stream_id, url)
                            info(f"{station_stream_url} }}\n")

                            self.add_track(station_stream_url, station_title, country_name, city_name, geo)

    def _fetch_json(self, id_):
        cached_json = os.path.join(CACHE_DIR, self.rg_version, f"{id_}.json")

        # Проверяем, существует ли кэшированный файл
        if os.path.exists(cached_json):
            with open(cached_json, "r") as file:
                data = json.load(file)
        else:
            # Выполняем запрос, если файл не существует
            response = requests.get(f"{CONTENT_PAGE}/{id_}/channels", timeout=30)
            response.raise_for_status()
            data = response.json()

            # Создаем директорию, если её нет
            os.makedirs(os.path.dirname(cached_json), exist_ok=True)

            # Сохраняем данные в кэшированный файл
            with open(cached_json, "w") as file:
                json.dump(data, file)

        return data

    def _get_redirect_url(self, id_, url):
        cached_url = os.path.join(CACHE_DIR, self.rg_version, f"{id_}.url")

        # Проверяем, существует ли кэшированный файл
        if os.path.exists(cached_url):
            with open(cached_url, "r") as file:
                data = json.load(file)
                return data["url"]
        else:
            # Выполняем запрос, если файл не существует
            response = requests.get(
                url, allow_redirects=False, timeout=30
            )  # Выполняем запрос, не следуя перенаправлениям
            if 300 <= response.status_code < 400:
                redirect_url = response.headers.get("Location")
                if redirect_url:
                    data = {"url": redirect_url}

                    # Создаем директорию, если её нет
                    os.makedirs(os.path.dirname(cached_url), exist_ok=True)

                    # Сохраняем данные в кэшированный файл
                    with open(cached_url, "w") as file:
                        json.dump(data, file)

                    return data["url"]
            else:
                raise ValueError("No redirect or unexpected response")


def info(str_):
    print(str_, end="", file=sys.stderr)


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
