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
    ">": "<",
    ">>": "<<",
    ")>": "<(",
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

VERBOSE_FLAG = False


def print_if_verbose(msg):
    global VERBOSE_FLAG
    if VERBOSE_FLAG:
        print(msg)


class JsonLoader(object):
    """
    Class to read from a filename/pathname containing one or more JSON files
    and make accessible a list of dicts.
    """
    def __init__(self, original_path):
        print_if_verbose("Using encoding {0}".format(sys.stdout.encoding)) # cp1252; can't process some UTF-8 stuff because windoze :(

        self.json_paths = self._get_file_paths(original_path)
        self.json_dicts = self._load_json_dicts()

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
        elif os.path.isdir(original_path):  # glob the files directly in dir
            path = os.path.join(original_path, "*.json")
            return glob.glob(path)
        else:
            raise Exception("Invalid path specified! "
                            "Please ensure that your given path points to either "
                            "a .json or a directory containing .json files.")

    def _load_json_dicts(self):
        """Loads one or more ORACC JSON files into one or more python dicts.
        If a JSON file is unable to be read, its corresponding dict will be empty.
        Returns:
            list (dict): loaded from the raw JSON files
        """
        json_dicts = []
        for json_path in self.json_paths:
            try:
                with open(json_path, encoding="utf_8_sig") as fd:
                    raw_str = fd.read()
                    json_dict = json.loads(raw_str)
                    json_dicts.append(json_dict)
            except Exception as e:
                print(e)
                json_dicts.append({})
        return json_dicts

    def get_json_dicts(self):
        return self.json_dicts # TODO make this into property


class JsonParser(object):
    """
    Class to take in a local JSON file and output a docx.
    """
    def __init__(self, json_dict):
        self.cdl_dict = json_dict
        self.l_reflist = [] # for repeat nodes

    def run(self):
        """Loads and parses given ORACC JSON, then saves the pieced-together
        text into a docx on disk.
        """
        textid = self.cdl_dict["textid"]
        print_if_verbose(
            "Parsing textid {0} from project {1}".format(textid, self.cdl_dict["project"])
        )
        doc = Document()
        res = self.parse_json(doc)
        self.print_doc(doc)
        self.save_docx(textid, doc)

    def parse_json(self, doc):
        """Walks through the JSON object and pieces together all the lemmas.
        No new sections like obverse/reverse yet.

        dict[cdl] is list
        dict[cdl][3] (or whatever index) has node == c; start parsing there
        dict[cdl][3][cdl] contains list of dicts with actual lemmas/line breaks
        """
        if not self.cdl_dict:
            return

        if self.cdl_dict["type"] != "cdl":
            print_if_verbose("Not a CDL-type JSON!\n")
            return

        nodes = self.cdl_dict["cdl"]
        for c_node in nodes:
            chunk = c_node
            res = self.traverse_c_node(chunk, doc)

    def save_docx(self, textid, doc):
        """Attempt to save the resulting docx file to current directory where
        script originally ran.
        Args:
            textid (str): ID of original JSON dict; basis of save name
                (eg. Q003456 -> Q003456.docx)
            doc (docx.Document): fully assembled docx object to be saved
        """
        try:
            name = textid + ".docx"
            doc.save(name)
            print_if_verbose("Saved doc as {0}".format(name))
        except Exception as e:
            print_if_verbose("Couldn't save docx! {0}".format(e))

    def print_doc(self, doc):
        """Utility function to print resulting fully assembled text to console.
        There will be no formatting such as italics. Super/subscripts may depend
        based on your terminal of choice.

        Args:
            doc (docx.Document): fully assembled text result to be printed
        """
        full_left_brackets = 0
        full_right_brackets = 0
        partial_left_brackets = 0
        partial_right_brackets = 0
        for p in doc.paragraphs:
            s = ""
            for r in p.runs:
                s += r.text
                if "[" in r.text:
                    full_left_brackets += 1
                elif "]" in r.text:
                    full_right_brackets += 1
                elif "⸢" in r.text:
                    partial_left_brackets += 1
                elif "⸣" in r.text:
                    partial_right_brackets += 1
            print(s)

        # Seeing if we're balanced or not
        print("[ count: {0}".format(full_left_brackets))
        print("] count: {0}".format(full_right_brackets))
        print("⸢ count: {0}".format(partial_left_brackets))
        print("⸣ count: {0}".format(partial_left_brackets))
        assert(full_left_brackets == full_right_brackets)
        assert(partial_left_brackets == partial_right_brackets)

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
            print_if_verbose("No id for this c-node!")
            return

        print_if_verbose("At c-node {0}".format(c_dict["id"]))

        for node in c_dict["cdl"]:
            if node["node"] == "c":
                self.traverse_c_node(node, doc)
            elif node["node"] == "d":
                self.parse_d_node(node, doc)
            elif node["node"] == "l":
                self.parse_l_node(node, doc)
            else:
                print_if_verbose("Unknown node type for node {0}".format(node))

    def parse_d_node(self, d_dict, doc):
        """Parses a D(iscontinuity) node and adds paragraphs to doc as needed.
        Types of d-node values:
          - line-start
          - obverse
          - reverse
          - object
          - surface
          - tablet
          - punct
          - nonx/nonw
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
            print_if_verbose("Unknown or noop d-value {0}".format(d_type))

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
        # Check if this frag's already been added
        ref = l_dict["ref"]
        if ref in self.l_reflist:
            print_if_verbose("Already added ref {0}, skipping".format(ref))
            return
        else:
            self.l_reflist.append(ref)

        last_paragraph = doc.paragraphs[-1]

        if l_dict["f"]["lang"] == "arc":  # eg. Aramaic
            print_if_verbose("Adding Aramaic node")
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
                print_if_verbose("Added number {0}".format(node_dict["form"]))
            else:
                print_if_verbose("Unknown l-node {0}".format(node_dict))
        last_paragraph.add_run(l_dict["f"].get("delim", ""))

    def _add_aramaic_frag(self, l_node, paragraph):
        """Adds Aramaic fragment to current paragraph with all needed formatting.
        See parse_l_node() description for an example L(emma) node.
        Args:
            l_node (dict): Aramaic lang node to be added
            paragraph (docx.text.paragraph.Paragraph): paragraph to add Aramaic fragment to
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
        self._add_pre_frag_symbols(gdl_node, paragraph)

        # Actual sign/word fragment
        word = self._convert_h(self._convert_2_or_3_subscript(gdl_node["v"]))
        r = paragraph.add_run(word)
        if word.islower():
            r.italic = True
        print_if_verbose("Added continuing sign {0}".format(word))

        self._add_post_frag_symbols(gdl_node, paragraph)

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

            self._add_pre_frag_symbols(gdl_node, paragraph)

            # Add the determinative to paragraph with needed stylings
            det = det_node.get("s", det_node.get("v", ""))
            det = self._convert_h(self._convert_2_or_3_subscript(det))
            r = paragraph.add_run(det)
            r.font.superscript = True
            print_if_verbose("Added determinative {0}".format(det))

            self._add_post_frag_symbols(gdl_node, paragraph)
        else:
            print_if_verbose("Unknown determinative position {0}".format(gdl_node["pos"]))

    def _add_logogram(self, gdl_node, paragraph):
        """Adds a standalone logogram to current paragraph, eg. LUGAL.
        Example L(emma) node (from rinap/rinap1/corpusjson/Q003627.json):
        {
            "node": "l",
            "frag": "LUGAL",
            "id": "Q003627.l00054",
            "ref": "Q003627.2.4",
            "inst": "šarri[king]N +.",
            "sig": "@rinap/rinap1%akk:LUGAL=šarru[king//king]N'N$šarri",
            "f": {
              "lang": "akk",
              "form": "LUGAL",
              "gdl": [ # begin gdl_node
                {
                  "s": "LUGAL",
                  "gdl_utf8": "𒈗",
                  "id": "Q003627.2.4.0",
                  "role": "logo",
                  "logolang": "sux"
                }
              ], # end gdl_node
              ...
        }
        """
        assert(gdl_node.get("s", "") and
               gdl_node.get("role", "") == "logo")

        self._add_pre_frag_symbols(gdl_node, paragraph)

        # Add actual logogram
        logogram = self._convert_h(self._convert_2_or_3_subscript(gdl_node["s"]))
        paragraph.add_run(logogram)
        print_if_verbose("Added logogram {0}".format(logogram))

        self._add_post_frag_symbols(gdl_node, paragraph)

        # Whatever delimiter follows, eg. - or space
        if gdl_node.get("delim", ""):
            paragraph.add_run(gdl_node["delim"])

    def _add_logogram_cluster(self, gdl_node, paragraph):
        """Adds >1 logograms to current paragraph, eg. GIC.TUG.PI.
        Example L(emma) node containing gdl node "gdl" (from rinap/rinap1/corpusjson/Q003627.json):
        {
            "node": "l",
            "frag": "MA.NA",
            "id": "Q003627.l00052",
            "ref": "Q003627.2.2",
            "inst": "manê[a unit of weight]N",
            "sig": "@rinap/rinap1%akk:MA.NA=manû[unit//a unit of weight]N'N$manê",
            "f": {
              "lang": "akk",
              "form": "MA.NA",
              "delim": " ",
              "gdl": [ # begin gdl_node
                {
                   "gg": "logo",
                   "gdl_type": "logo",
                   "group": [
                     {
                       "s": "MA",
                       "gdl_utf8": "𒈠",
                       "id": "Q003627.2.2.0",
                       "role": "logo",
                       "logolang": "sux",
                       "delim": "."
                     },
                     {
                       "s": "NA",
                       "gdl_utf8": "𒈾",
                       "id": "Q003627.2.2.1",
                       "role": "logo",
                       "logolang": "sux"
                     }
                  ]
                }
            ], # end gdl_node
            ...
        }
        """
        logo_group_dict = gdl_node["group"]
        for logo_dict in logo_group_dict:
            if "s" in logo_dict:
                self._add_logogram(logo_dict, paragraph)
            elif "det" in logo_dict:
                self._add_determinative(logo_dict, paragraph)
            else:
                print_if_verbose("Non-sign or determinative found in logogram cluster {0}".format(logo_dict))
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

    def _add_pre_frag_symbols(self, gdl_node, paragraph):
        """Adds any symbols that come before the actual text fragment.
        These chars may be added: [ ⸢ < <<
        Args:
            gdl_node (dict): dict of L(emma) node's "gdl" property
            paragraph (docx.text.paragraph.Paragraph): paragraph to add to
        """
        # Full fragment break start
        if gdl_node.get("breakStart", ""):
            paragraph.add_run("[")

        # o for whatever reason may include [ or ], but this is already taken
        # care of by breakStart and breakEnd. Leave o to just be eg. ( ) < >>
        o_frag = gdl_node.get("o", "").strip("[]")
        if "id" in gdl_node and gdl_node.get("statusStart", "") == gdl_node["id"]:
            # o needs to be mirrored first to be an opener frag like ( or < or <<
            o_mirror = closing_punct_mirror[o_frag]
            paragraph.add_run(o_mirror)

        elif gdl_node.get("statusStart", "") == 1:
            # o should already be an opener frag like ( or < or <<
            paragraph.add_run(o_frag)

        # Partial fragment break start
        if gdl_node.get("ho", ""):
            paragraph.add_run("⸢")

    def _add_post_frag_symbols(self, gdl_node, paragraph):
        """Adds any symbols that come after the actual text fragment.
        These chars may be added: ? ⸣ > >>
        Args:
            gdl_node (dict): dict of L(emma) node's "gdl" property
            paragraph (docx.text.paragraph.Paragraph): paragraph to add to
        """
        # Unknown/uncertain sign
        if gdl_node.get("queried", ""):
            r = paragraph.add_run("?")
            r.font.superscript = True

        # Partial fragment break end
        if gdl_node.get("hc", ""):
            paragraph.add_run("⸣")

        # o for whatever reason may include [ or ], but this is already taken
        # care of by breakStart and breakEnd. Leave o to just be eg. ( ) < >>
        o_frag = gdl_node.get("o", "").strip("[]")
        if "id" in gdl_node and gdl_node.get("statusStart", "") == gdl_node["id"]:
            # o should already be a closer frag like ) or > or >>
            paragraph.add_run(o_frag)

        # Full fragment break end
        if gdl_node.get("breakEnd", ""):
            paragraph.add_run("]")

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
        print_if_verbose("You shouldn't be here!")
        return sign

    def _convert_h(self, sign):
        """Replaces h with ḫ, capital or lowercase. TODO Might not actually need this...
        Args:
            sign (str): transliterated sign, eg. ah or HA
        """
        if sign.islower():
            return sign.replace("h", "ḫ")
        else:
            return sign.replace("H", "Ḫ")


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
    parser.add_argument('--verbose', '-v', required=False, action="store_true",
                        help='Enable verbose mode during parsing')
    args = parser.parse_args()

    if args.verbose:
        global VERBOSE_FLAG
        VERBOSE_FLAG = True

    jl = JsonLoader(args.file)
    for json_dict in jl.get_json_dicts():
        jp = JsonParser(json_dict)
        jp.run()


if __name__ == "__main__":
    main()
