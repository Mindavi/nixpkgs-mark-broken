#! /usr/bin/env nix-shell
#! nix-shell -i python3 --pure -p "pkgs.python3.withPackages(ps: with ps; [ requests ])" nix

import argparse
from html.parser import HTMLParser
import pprint
import sys

class MyHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_table_row = False
        self.table_column = -1
        # Aborted, Dependency failed, Failed, Succeeded, Queued
        self.build_status = ""
        self.build_url = ""
        self.attribute_name = ""
        # { "name.platform": "status" }
        self.build_table = dict()
    def handle_starttag(self, tag, attrs):
        if self.in_table:
            if tag == "tr":
                self.in_table_row = True
            if tag == "td":
                self.table_column += 1
            attrs_map = dict()
            for key, value in attrs:
                attrs_map[key] = value
            if tag == "a":
                self.build_url = attrs_map["href"]
            if "class" in attrs_map:
                if attrs_map["class"] == "build-status":
                    self.build_status = attrs_map["title"]
        if tag == "tbody":
            self.in_table = True

    def handle_endtag(self, tag):
        if self.in_table:
            if tag == "tr":
                self.in_table_row = False
                self.table_column = -1
                # Not the build info table
                if not self.attribute_name or not self.build_status:
                    return
                assert(self.build_url)
                self.build_table[self.attribute_name] = {"status": self.build_status, "url": self.build_url }

                self.build_status = ""
                self.build_url = ""
                self.attribute_name = ""
        if tag == "tbody":
            self.in_table = False

    def handle_data(self, data):
        if self.in_table:
            data = data.strip()
            if not data:
                return
            if self.table_column == 2:
                self.attribute_name = data

    def get_build_statuses(self):
        return self.build_table

parser = MyHTMLParser()

with open('nixos-hydra-full.html', 'r') as html_file:
    for line in html_file:
        line = line.strip()
        parser.feed(line)

pp = pprint.PrettyPrinter(indent=4)
pp.pprint(parser.get_build_statuses())

#print(parser.get_build_statuses()["aflplusplus.x86_64-linux"])

