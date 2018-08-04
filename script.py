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

# Used to transform eg. a2 to á in the final result docx.
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
    def __init__(self, original_path, verbose):
        self.verbose = verbose
        self.l_reflist = [] # for repeat nodes
        self.file_paths = self._get_file_paths(original_path)

        self.print_if_verbose("Using encoding {0}".format(sys.stdout.encoding)) # cp1252; can't process some UTF-8 stuff because windoze :(

    def _get_file_paths(self, original_path):
        """Returns a list of one or more ORACC JSON files to read. Passing
        in a directory will result in a list of all JSONs in that directory.
        Args:
            original_path (str): Relative or absolute path to either one
                JSON file or a directory
        Returns:
            list: List of one or more path strings to JSON files
        Raises:
            Exception: if original_path is invalid
        """
        if os.path.isfile(original_path):
            return [original_path]
        elif os.path.isdir(path):  # glob the files directly in dir
            path = os.path.join(path, "*.json")
            return glob.glob(path)
        else:
            raise Exception("Invalid path specified! "
                            "Please ensure that your given path points to either "
                            "a .json or a directory containing .json files.")

    def run(self, json_name=None):
        """Loads and parses given ORACC JSON, then saves the pieced-together
        text into a docx on disk.

        Args:
            json_name (str): TODO not doing anything atm
        """
        for path in self.file_paths:
            self.print_if_verbose("Parsing file at {0}".format(path))
            cdl_dict = self.load_json(path)
            doc = Document()
            res = self.parse_json(cdl_dict, doc)
            self.print_doc(doc)
            self.save_docx(path, doc)

    def print_doc(self, doc):
        """Utility function to print resulting fully assembled text to console.
        There will be no formatting such as italics. Super/subscripts may depend
        based on your terminal of choice.

        Args:
            doc (docx.Document): fully assembled text result to be printed
        """
        # full_left_brackets = 0
        # full_right_brackets = 0
        # partial_left_brackets = 0
        # partial_right_brackets = 0
        for p in doc.paragraphs:
            s = ""
            # for r in p.runs:
            #     s += r.text
            #     if r == "[":
            #         full_left_brackets += 1
            #     elif r == "]":
            #         full_right_brackets += 1
            #     elif r == "⸢":
            #         partial_left_brackets += 1
            #     elif r == "⸣":
            #         partial_right_brackets += 1
            print(s)

        # Seeing if we're balanced or not. TODO none of these get bracket properly, it's embedded in run with text
        # print("[ count: {0}".format(full_left_brackets))
        # print("] count: {0}".format(full_right_brackets))
        # print("⸢ count: {0}".format(partial_left_brackets))
        # print("⸣ count: {0}".format(partial_left_brackets))
        # assert(full_left_brackets == full_right_brackets)
        # assert(partial_left_brackets == partial_right_brackets)

    def load_json(self, path):
        """Loads an ORACC JSON file into a python dict.
        Args:
            path (str): Relative or absolute path to JSON to read.
        Returns:
            dict: loaded from the raw JSON. Empty if JSON is unable to be read.
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
        Will further traverse down a C(hunk), D(iscontinuity), or L(emma)
        node as needed.

        Args:
            c_dict (dict): Corresponds to the very first C node encountered
                in an ORACC JSON. Contains more C, D, or L nodes that may
                further be nested.
            doc (docx.Document): docx object to append lemmas to
        """
        if not c_dict.get("id", ""):
            self.print_if_verbose("No id for this c-node!")
            return
        #if c_dict.get("type", "") == "phrase":
            #self.print_if_verbose("Phrase c-node here, don't mind me")

        self.print_if_verbose("At c-node {0}".format(c_dict["id"]))

        for node in c_dict["cdl"]:
            if node["node"] == "c":
                self.traverse_c_node(node, doc)
            elif node["node"] == "d":
                self.parse_d_node(node, doc)
            elif node["node"] == "l":
                self.parse_l_node(node, doc)
            else:
                self.print_if_verbose("Unknown node type for node {0}".format(node))

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
            #p.add_run(d_dict.get("label", "") + " ") # XXX don't know if I need this

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
            self.print_if_verbose("Unknown d-value {0}".format(d_type))

    def parse_l_node(self, l_dict, doc):
        """Gets L(emma) node text, formats it, and adds it to the last paragraph of doc.
        L nodes may contain either an Akkadian or Aramaic lemma.
        Example of Akkadian L node which this function will work on (in rinap/rinap1/corpusjson/Q003414.json):
        {
            "node": "l",
            "frag": "{d}[(...)",
            "id": "Q003414.l000a0",
            "ref": "Q003414.2.5",
            "inst": "u",
            "f": {
                "lang": "akk",
                "form": "{d}x",
                "delim": " ",
                "gdl": [
                    {
                        "det": "semantic",
                        "pos": "pre",
                        "seq": [
                          {
                            "v": "d",
                            "gdl_utf8": "𒀭",
                            "id": "Q003414.2.5.0"
                          }
                        ]
                    },
                    {
                        "x": "ellipsis",
                        "id": "Q003414.2.5.1",
                        "breakStart": "1",
                        "statusStart": "Q003414.2.5.1",
                        "break": "missing",
                        "o": ")"
                    }
                ],
                "pos": "u"
            }
        }

        Example of Aramaic L node which this function will work on (in rinap/rinap1/corpusjson/Q003633.json):
        {
            "node": "l",
            "frag": "mnn",
            "id": "Q003633.l00075",
            "ref": "Q003633.1.1",
            "inst": "%arc:mnn=",
            "f": {
                "lang": "arc",
                "form": "mnn"
            }
        }

        Args:
            l_dict (dict): dict version of an L node above
            doc (docx.Document): document object to append lemma to
        """
        assert(l_dict["node"] == "l")

        # Check if this frag's already been added
        ref = l_dict["ref"]
        if ref in self.l_reflist:
            self.print_if_verbose("Already added ref {0}, skipping".format(ref))
            return
        else:
            self.l_reflist.append(ref)

        l_value = l_dict["frag"]
        #pprint(l_dict)

        last_paragraph = doc.paragraphs[-1]

        if l_dict["f"]["lang"] == "arc":  # eg. Aramaic
            self.print_if_verbose("Adding Aramaic node")
            self._add_aramaic_frag(l_dict, last_paragraph)
            return

        gdl_list = l_dict["f"]["gdl"]

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
                self._add_ellipsis(node_dict, l_dict, last_paragraph)
            elif "n" in node_dict:
                last_paragraph.add_run(node_dict["form"])
                self.print_if_verbose("Added number {0}".format(node_dict["form"]))
            else:
                self.print_if_verbose("Unknown l-node {0}".format(node_dict))
        last_paragraph.add_run(l_dict["f"].get("delim", ""))

    def _add_aramaic_frag(self, l_node, paragraph):
        """Adds Aramaic fragment to current paragraph with all needed formatting.
        See parse_l_node() description for an example L(emma) node.
        Args:
            l_node (dict): Aramaic lang node to be added
            paragraph (docx...paragraph): paragraph to add Aramaic fragment to
        """
        frag = l_node.get("frag", "")
        for char in frag:
            r = paragraph.add_run(char)
            if char.isalpha():
                r.italic = True
        # Aramaic nodes have no "delim", but should be separated with space
        paragraph.add_run(" ")

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
        # Starting full bracket - TODO switch to not rely on dict, if no breakEnd just use o
        if gdl_node.get("breakStart", ""):
            bracket = gdl_node.get("o")
            if gdl_node.get("breakEnd", ""): # use opposite of what's in o, as it's for end bracket
                paragraph.add_run(closing_punct_mirror[bracket])
            else: # this sign only has starting bracket but not end
                paragraph.add_run(bracket)

        # Upper left bracket
        if gdl_node.get("ho", ""):
            paragraph.add_run("⸢")

        # Actual sign/word fragment
        word = self._convert_h(self._convert_2_or_3_subscript(gdl_node["v"]))
        r = paragraph.add_run(word)
        if word.islower():
            r.italic = True
        self.print_if_verbose("Added continuing sign {0}".format(word))

        # Unknown/uncertain sign
        if gdl_node.get("queried", ""):
            r = paragraph.add_run("?")
            r.font.superscript = True

        # Upper right bracket
        if gdl_node.get("hc", ""):
            paragraph.add_run("⸣")

        # Closing full bracket - TODO switch to breakEnd
        if gdl_node.get("o", "") in closing_punct_mirror:
            paragraph.add_run(gdl_node["o"])

        # Whatever delimiter follows, eg. - or space
        if gdl_node.get("delim", ""):
            paragraph.add_run(gdl_node["delim"])

    def _add_determinative(self, gdl_node, paragraph):
        """Adds determinative to given paragraph and adds necessary styling.
        Example of a node that this would work on (from rinap/rinap1/corpusjson/Q003414.json):
        {
            "det": "semantic",
            "pos": "post",
            "seq": [
                {
                    "s": "KI",
                    "gdl_utf8": "𒆠",
                    "id": "Q003414.2.2.2",
                    "role": "logo",
                    "logolang": "sux"
                }
            ]
        }

        Args:
            gdl_node (dict): dict representation of a "det" node. These will
                always occur as a member of a L(emma) node's gdl list.
            paragraph (docx.text.paragraph.Paragraph): Paragraph object
                that will append the new determinative
        """
        assert(gdl_node.get("det", "") == "semantic")

        if gdl_node["pos"] == "pre" or gdl_node["pos"] == "post":
            det_node = gdl_node["seq"][0]

            # Starting full bracket
            if det_node.get("breakStart", ""):
                paragraph.add_run("[")

            # Upper left bracket
            if det_node.get("ho", ""):
                paragraph.add_run("⸢")

            # Add the determinative to paragraph with needed stylings
            det = det_node.get("s", det_node.get("v", ""))
            det = self._convert_h(self._convert_2_or_3_subscript(det))
            r = paragraph.add_run(det)
            r.font.superscript = True
            self.print_if_verbose("Added determinative {0}".format(det))

            # Unknown/uncertain sign
            if det_node.get("queried", ""):
                r = paragraph.add_run("?")
                r.font.superscript = True

            # Upper right bracket
            if det_node.get("hc", ""):
                paragraph.add_run("⸣")

            # Closing full bracket
            if det_node.get("o", "") in closing_punct_mirror:
                det += det_node["o"]
        else:
            self.print_if_verbose("Unknown determinative position {0}".format(gdl_node["pos"]))

    def _add_logogram(self, gdl_node, paragraph):
        """Adds a standalone logogram to current paragraph.
        eg.
        {
          "s": "BAD₃",
          "role": "logo",
          "delim": "-"
        },
        """
        #pprint(gdl_node)
        assert(gdl_node.get("s", "") and
               gdl_node.get("role", "") == "logo")

        # Starting full bracket
        if gdl_node.get("breakStart", ""):
            paragraph.add_run("[")

        # Upper left bracket
        if gdl_node.get("ho", ""):
            paragraph.add_run("⸢")

        # Actual logogram
        logogram = self._convert_h(self._convert_2_or_3_subscript(gdl_node["s"]))
        paragraph.add_run(logogram)
        self.print_if_verbose("Added logogram {0}".format(logogram))

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
            if "s" in logo_dict:
                self._add_logogram(logo_dict, paragraph)
            elif "det" in logo_dict:
                self._add_determinative(logo_dict, paragraph)
            else:
                self.print_if_verbose("Non-sign or determinative found in logogram cluster {0}".format(logo_dict))
        paragraph.add_run(gdl_node.get("delim", ""))

    def _add_ellipsis(self, node_dict, l_node, paragraph):
        """Adds in things like (...), [...]
        Start at [ (or beginning) and end at next delimiter (or end).
        Can't figure out how to correctly create from scratch, so just substring it for now...
        """
        frag_raw = l_node["frag"]

        start_index = frag_raw.find("[")
        if start_index == -1:
            start_index = 0

        if "delim" in node_dict:
            end_index = frag_raw.find(node_dict["delim"]) + 1
        else:
            end_index = None

        frag = frag_raw[start_index:end_index]
        paragraph.add_run(frag)

    def _convert_2_or_3_subscript(self, sign):
        """Converts a sign containing a numerical 2 or 3 subscript to have its
        first vowel be properly accented.
        Args:
            sign (str): transliterated string of sign with some subscript,
                 eg. bi₂
        Returns:
            str: transliterated string of sign with subscript transformed into
                 accented mark, eg. bí for above example
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
        self.print_if_verbose("You shouldn't be here!")
        return sign

    def _convert_h(self, sign):
        """Replaces h with ḫ, capital or lowercase. TODO Might not actually need this...
        Args:
            sign ():
        """
        if sign.islower():
            return sign.replace("h", "ḫ")
        else:
            return sign.replace("H", "Ḫ")

    def parse_json(self, cdl_dict, doc):
        """
        Walks through the JSON object and pieces together all the lemmas.
        No formatting yet; no dealing with line breaks or new sections like obverse/reverse.

        dict[cdl] is list
        dict[cdl][3] (or whatever index) has node == c; start parsing there
        dict[cdl][3][cdl] contains list of dicts with actual lemmas/line breaks
        """
        if not cdl_dict:
            return

        if cdl_dict["type"] != "cdl":
            self.print_if_verbose("Not a CDL-type JSON!\n")
            return

        nodes = cdl_dict["cdl"]
        for c_node in nodes:
            chunk = c_node
            res = self.traverse_c_node(chunk, doc)

    def save_docx(self, path, doc):
        """Attempt to save the resulting docx file to current directory.
        Args:
            path (str): Relative or absolute path to original JSON file
            doc (docx.Document): fully assembled docx object to be saved
        """
        try:
            name = os.path.basename(path).split(".json")[0]
            doc.save(name + ".docx")
            self.print_if_verbose("Saved doc as {0}.docx".format(name))
        except Exception as e:
            self.print_if_verbose("Couldn't save docx! {0}".format(e))

    def print_if_verbose(self, msg):
        if self.verbose:
            print(msg)


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
    parser.add_argument('--verbose', '-v', required=False, default=True, action="store_true",
                        help='Enable verbose mode during parsing')
    args = parser.parse_args()

    jp = JsonParser(args.file, args.verbose)
    jp.run()


if __name__ == "__main__":
    main()
