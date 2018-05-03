#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys
import json
import argparse

from docx import Document

"""
Parses one or more JSON files and outputs a well-formatted DOC(X).
na-pul-tu ⸢a⸣-du-ú M.zum-bu-ta-a-nu -> upper bracket not visible in UTF-8 but u2 is fine, is it UTF-16 then? What about super/subscripts?
"""

"""
Types of nodes:
c(hunk): chunk of text; may be the entire text, a sentence/unit, clause, phrase, etc...
l(emma): text token (inflected, conjugated, etc.) along with its lemmatization ("dictionary" form and specific meaning)
d(iscontinuity): line break, surface transition, or damage
"""

class JsonParser(object):
    """
    Class to take in a local JSON file and output an XXX.
    """
    def __init__(self, path):
        self.file_path = path
        
    def run(self):
        cdl_dict = self.load_json(self.file_path)
        res = self.parse_json(cdl_dict)
        print(res)
        
    def load_json(self, path):
        """
        Loads a JSON file into a dict.
        """
        try:
            with open(path, encoding="utf_8_sig") as fd:
                raw_str = fd.read()
                json_dict = json.loads(json.dumps(raw_str))
                return json_dict
        except Exception as e:
            print(e)
            return {}
            
    def traverse_c_node(self, c_dict):
        assert(c_dict["node"] == "c")
        print("At c-node {0}".format(c_dict["id"]))
        for node in c_dict["cdl"]:
            if node["node"] == "c":
                self.traverse_c_node(node)
            elif node["node"] == "d":
                self.parse_d_node(node)
            elif node["node"] == "l":
                self.parse_l_node(node)
            
    def parse_d_node(self, d_dict):
        assert(d_dict["node"] == "d")
        print(d_dict["type"])
        
    def parse_l_node(self, l_dict):
        assert(l_dict["node"] == "l")
        print(l_dict["frag"] + " ")

    def parse_json(self, cdl_dict):
        """
        Walks through the JSON object and pieces together all the lemmas.
        No formatting yet; no dealing with line breaks or new sections like obverse/reverse.
        
        Should also probably make this recursive or something, or make use of separate functions
        for each node type...
        
        dict[cdl] is list
        dict[cdl][3] (or whatever index) has node == c; start parsing there
        dict[cdl][3][cdl] contains list of dicts with actual lemmas/line breaks
        """
        print(cdl_dict)
        if not cdl_dict:
            return
        if cdl_dict["type"] != "cdl":
            print("Not a CDL-type JSON!\n")
            return
        nodes = cdl_dict["cdl"]
        for c_node in nodes:
            chunk = c_node["cdl"]
            print(chunk)
            self.traverse_c_node(chunk)

    def get_file_list():
        """
        In directory mode, takes in directory path and returns
        a list of parseable JSON files.
        """
        pass

    def create_docx(self):
        pass


class HtmlParser(object):
    """
    Class to take in a (local or remote) HTML file from XXXX
    and output an XXX.
    
    eg. http://oracc.museum.upenn.edu/rinap/rinap1/Q003414/html
    """
    def __init__(self, *args, **kwargs):
        pass


def main():
    """
    Parses arguments, determines which mode (json or html) to use.
    
    json: [--file /path/to/json] [--directory /path (. by default)]
    html: [--file /path/to/html] [--]
    """
    parser = argparse.ArgumentParser(description='Parse your shit here.')
    parser.add_argument('--file', '-f', required=True,
                        help='A path to the JSON file to parse into DOCX')
    args = parser.parse_args()
    
    print("Using encoding {0}".format(sys.stdout.encoding)) # cp1252; can't process some UTF-8 stuff because wangblows :(
    
    jp = JsonParser(args.file)
    jp.run()


if __name__ == "__main__":
    main()