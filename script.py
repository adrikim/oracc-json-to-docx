#!/usr/bin/env python3
# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import sys
import json
import glob
import argparse
from pprint import pprint

from docx import Document

"""
Parses one or more JSON files and outputs a well-formatted DOC(X) file.

Types of nodes:
c(hunk): chunk of text; may be the entire text, a sentence/unit, clause, phrase, etc...
l(emma): text token (inflected, conjugated, etc.) along with its lemmatization ("dictionary" form and specific meaning)
d(iscontinuity): line break, surface transition, or damage
"""

closing_punct_mirror = {
    "]": "[",
    ")": "(",
    ")]": "[(",
}

vowel_subscript_to_accent_map = {
    "a": {
        "two": "á",
        "three": "à",
    },
    "e": {
        "two": "é",
        "three": "è",
    },
    "i": {
        "two": "í",
        "three": "ì",
    },
    "u": {
        "two": "ú",
        "three": "ù",
    },
}

class JsonParser(object):
    """
    Class to take in a local JSON file and output a docx.
    """
    def __init__(self, path):
        if os.path.isfile(path):
            self.file_paths = [path]
        elif os.path.isdir(path):  # glob the files directly in dir
            path = os.path.join(path, "*.json")
            self.file_paths = glob.glob(path)
        else:
            raise Exception("Invalid path specified!")
        
    def run(self, json_name=None):
        for path in self.file_paths:
            print("Parsing file at {0}".format(path))
            cdl_dict = self.load_json(path)
            doc = Document()
            res = self.parse_json(cdl_dict, doc)
            self.print_doc(doc)
            self.save_docx(path, doc)

    def print_doc(self, doc):
        for p in doc.paragraphs:
            s = ""
            for r in p.runs:
                s += r.text
            print(s)
        
    def load_json(self, path):
        """
        Loads a JSON file into a dict.
        """
        try:
            with open(path, encoding="utf_8_sig") as fd:
                raw_str = fd.read()
                json_dict = json.loads(raw_str)
                return json_dict
        except Exception as e:
            print(e)
            return {}
            
    def traverse_c_node(self, c_dict, doc):
        """Decides what to do for each of the nodes in a c-node's node list.
        """
        if not c_dict.get("id", ""):
            return
        print("At c-node {0}".format(c_dict["id"]))
        for node in c_dict["cdl"]:
            if node["node"] == "c":
                self.traverse_c_node(node, doc)
            elif node["node"] == "d":
                self.parse_d_node(node, doc)
            elif node["node"] == "l":
                self.parse_l_node(node, doc)
            else:
                print("Unknown node type for node {0}".format(node))

    def parse_d_node(self, d_dict, doc):
        """Parses a D-node and adds paragraphs to doc as needed.
        Types of d-node values:
          - line-start
          - obverse
          - reverse
          - object
          - surface
          - tablet
          - punct
          - nonx
        """
        assert(d_dict["node"] == "d")
        d_type = d_dict["type"]
        if d_type == "line-start":
            doc.add_paragraph()
        elif d_type == "obverse":
            p = doc.add_paragraph()
            p.add_run("Obverse")
            doc.add_paragraph()
        elif d_type == "reverse":
            p = doc.add_paragraph()
            p.add_run("Reverse")
            doc.add_paragraph()
        elif d_type == "punct":
            p = doc.paragraphs[-1]
            p.add_run(d_dict["frag"])
            p.add_run(d_dict.get("delim", ""))
        else:
            print("Unknown d-value {0}".format(d_type))

    def parse_l_node(self, l_dict, doc):
        """Gets L-node text, formats it, and adds it to the last paragraph of doc.
        """
        assert(l_dict["node"] == "l")
        if not l_dict["f"].get("gdl", ""):  # eg. Aramaic
            return
        l_value = l_dict["frag"]
        #pprint(l_dict)

        gdl_list = l_dict["f"]["gdl"]
        last_paragraph = doc.paragraphs[-1]

        for node_dict in gdl_list:
            if "s" in node_dict:
                self._add_logogram(node_dict, last_paragraph)
            elif "v" in node_dict:
                self._add_continuing_sign_form(node_dict, last_paragraph)
            elif "det" in node_dict:
                self._add_determinative(node_dict, last_paragraph)
            elif "gg" in node_dict:
                self._add_logogram_cluster(node_dict, last_paragraph)
            elif "x" in node_dict:
                self._add_ellipsis(l_dict, last_paragraph)
            elif "n" in node_dict:
                last_paragraph.add_run(node_dict["form"])
            else:
                print("Unknown l-node {0}".format(node_dict))
        last_paragraph.add_run(l_dict["f"].get("delim", ""))

    def _add_continuing_sign_form(self, gdl_node, paragraph):
        """Adds eg. tu- to the current paragraph.
        eg.
        {
          "v": "a",
          "queried": "1",
          "ho": "1",
          "delim": "-"
        }
        """
        # Starting full bracket
        if gdl_node.get("breakStart", ""):
            paragraph.add_run("[")

        # Upper left bracket
        if gdl_node.get("ho", ""):
            paragraph.add_run("⸢")

        # Actual sign/word fragment
        word = self._convert_h(self._convert_2_or_3_subscript(gdl_node["v"]))
        r = paragraph.add_run(word)
        if word.islower():
            r.italic = True

        # Unknown/uncertain sign
        if gdl_node.get("queried", ""):
            r = paragraph.add_run("?")
            r.font.superscript = True

        # Upper right bracket
        if gdl_node.get("hc", ""):
            paragraph.add_run("⸣")

        # Closing full bracket
        if gdl_node.get("o", "") in closing_punct_mirror:
            paragraph.add_run(gdl_node["o"])

        # Whatever delimiter follows, eg. - or space
        if gdl_node.get("delim", ""):
            paragraph.add_run(gdl_node["delim"])

    def _add_determinative(self, gdl_node, paragraph):
        """Adds determinative to paragraph.
        For ones like:
        {
            "det": "semantic",
            "pos": "post",
            "seq": [
               {
                  "s": "ki",
                  "role": "logo", // for all dets/sumerograms
                  "logolang": "sux"
                }
            ]
        }
        """
        assert(gdl_node.get("det", "") == "semantic")
        if gdl_node["pos"] == "pre" or gdl_node["pos"] == "post":
            det_node = gdl_node["seq"][0]
            det = det_node.get("s", det_node.get("v", ""))
            det = self._convert_h(self._convert_2_or_3_subscript(det))
            r = paragraph.add_run(det)  # TODO can seq have >1 member? Doesn't seem so, see {m}{d}
            r.font.superscript = True
        else:
            print("Unknown determinative position {0}".format(gdl_node["pos"]))

    def _add_logogram(self, gdl_node, paragraph):
        """Adds a standalone logogram to current paragraph.
        eg.
        {
          "s": "BAD₃",
          "role": "logo",
          "delim": "-"
        },
        """
        assert(gdl_node.get("s") and
               gdl_node["role"] == "logo")

        # Starting full bracket
        if gdl_node.get("breakStart", ""):
            paragraph.add_run("[")

        # Upper left bracket
        if gdl_node.get("ho", ""):
            paragraph.add_run("⸢")

        # Actual logogram
        logogram = self._convert_h(self._convert_2_or_3_subscript(gdl_node["s"]))
        paragraph.add_run(logogram)

        # Unknown/uncertain sign
        if gdl_node.get("queried", ""):
            r = paragraph.add_run("?")
            r.font.superscript = True

        # Upper right bracket
        if gdl_node.get("hc", ""):
            paragraph.add_run("⸣")

        # Closing full bracket
        if gdl_node.get("o", "") in closing_punct_mirror:
            paragraph.add_run(gdl_node["o"])

        # Whatever delimiter follows, eg. - or space
        if gdl_node.get("delim", ""):
            paragraph.add_run(gdl_node["delim"])

    def _add_logogram_cluster(self, gdl_node, paragraph):
        """Adds >1 logograms to current paragraph, eg. GIC.TUG.PI
        eg.
        {
          'gg': 'logo',
          'group': [{
            's': 'KUR', 
            'break': 'damaged', 
            'ho': '1', 
            'delim': '.'
          }, 
          {
             's': 'KUR', 
             'break': 'damaged', 
             'hc': '1'
          }
        ]}
        """
        logo_group_dict = gdl_node["group"]
        for logo_dict in logo_group_dict:
            self._add_logogram(logo_dict, paragraph)
        paragraph.add_run(gdl_node.get("delim", ""))

    def _add_ellipsis(self, l_node, paragraph):
        """Adds in things like (...), [...]
        Can't figure out how to correctly create from scratch, so just substring it for now...
        """
        frag_raw = l_node["frag"]
        index = frag_raw.find("[")
        if index == -1:
            index = 0
        frag = frag_raw[index:]
        paragraph.add_run(frag)

    def _convert_2_or_3_subscript(self, sign):
        """Converts a sign containing a numerical 2 or 3 subscript to have its
        first vowel be properly accented.
        """
        if not sign[-1].isdigit(): # No subscript # here
            return sign
        if sign[-2].isdigit():  # number was eg. 12 or 13- not just 2 or 3
            return sign

        if sign[-1] == "₂":
            subscript_num = "two"
        elif sign[-1] == "₃":
            subscript_num = "three"
        else:
            return sign

        # First vowel in sign will get the accent mark
        for char in sign:
            char_lower = char.lower()
            if char_lower in "aeiu":
                accented_char = vowel_subscript_to_accent_map[char_lower][subscript_num]
                if char.isupper():
                    accented_char = accented_char.upper()
                return sign[:-1].replace(char, accented_char, 1)
        print("You shouldn't be here!")
        return sign
                
    def _convert_h(self, sign):
        """Replaces h with ḫ, capital or lowercase.
        """
        if sign.islower():
            return sign.replace("h", "ḫ")
        else:
            return sign.replace("H", "Ḫ")

    def parse_json(self, cdl_dict, doc):
        """
        Walks through the JSON object and pieces together all the lemmas.
        No formatting yet; no dealing with line breaks or new sections like obverse/reverse.
        
        Should also probably make this recursive or something, or make use of separate functions
        for each node type...
        
        dict[cdl] is list
        dict[cdl][3] (or whatever index) has node == c; start parsing there
        dict[cdl][3][cdl] contains list of dicts with actual lemmas/line breaks
        """
        if not cdl_dict:
            return
        if cdl_dict["type"] != "cdl":
            print("Not a CDL-type JSON!\n")
            return
        nodes = cdl_dict["cdl"]
        for c_node in nodes:
            chunk = c_node
            res = self.traverse_c_node(chunk, doc)

    def save_docx(self, path, doc):
        """Save the resulting docx file to current directory.
        """
        try:
            name = os.path.basename(path).split(".json")[0]
            doc.save(name + ".docx")
            print("Saved doc as {0}.docx".format(name))
        except Exception as e:
            print("Couldn't save docx! {0}".format(e))


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
                        help='A path (file or directory) to the JSON file to parse into DOCX')
    args = parser.parse_args()
    
    print("Using encoding {0}".format(sys.stdout.encoding)) # cp1252; can't process some UTF-8 stuff because wangblows :(
    
    jp = JsonParser(args.file)
    jp.run()


if __name__ == "__main__":
    main()
