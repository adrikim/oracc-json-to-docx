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
#from bs4 import BeautifulSoup

"""
Parses one or more JSON files and outputs well-formatted DOC(X) file(s).

Types of nodes:
c(hunk): chunk of text; may be the entire text, a sentence/unit, clause, phrase, etc...
l(emma): text token (inflected, conjugated, etc.) along with its lemmatization ("dictionary" form and specific meaning)
d(iscontinuity): line break, surface transition, or damage
"""

closing_punct_mirror = {
    "]": "[",
    ")": "(",
    "›": "‹",
    "»": "«",
    ")›": "‹(",
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
    and make accessible a list of dicts (one per JSON/exemplar).
    """
    def __init__(self, original_path, use_exemplar):
        print_if_verbose("Using encoding {0}".format(sys.stdout.encoding)) # cp1252; can't process some UTF-8 stuff because windoze :(

        self.use_exemplar = use_exemplar
        self.catalogue_dict = None
        self.json_paths = self._get_file_paths(original_path)
        self.json_dicts = self._load_json_dicts()

    def _get_file_paths(self, original_path):
        """Returns a list of one or more ORACC JSON files to read. Passing
        in a directory will result in a list of all JSONs in that directory.
        Args:
            original_path (str): Relative or absolute path to either one
                JSON file or a directory of JSON files
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
        If a JSON file is unable to be read, its corresponding dict will be empty,
        save for its original path.
        Returns:
            list (dict): loaded from the raw JSON files
        """
        json_dicts = []
        for json_path in self.json_paths:
            try:
                with open(json_path, encoding="utf_8_sig") as fd:
                    raw_str = fd.read()
                    json_dict = json.loads(raw_str)

                    json_dict["original_path"] = json_path

                    #if self.use_exemplar:
                        #json_dict["docx_name"] = self.get_exemplar_name(json_path) # TODO put exemplar name at top of docx instead when imported
                    #else:
                        #json_dict["docx_name"] = os.path.basename(json_path).split(".json")[0]

                    # TODO: this is temporary
                    json_dict["exemplars"] = self.get_exemplar_name(json_path)
                    # TODO end temporary
                    json_dict["docx_name"] = os.path.basename(json_path).split(".json")[0]

                    json_dicts.append(json_dict)
            except Exception as e:
                print("Could not load {0} to dict: {1}".format(json_path, e))
                print("If this is an encoding error, check that the venv is based on py3, not py2")
                json_dicts.append({
                    "original_path": json_path,
                })
        return json_dicts

    def get_json_dicts(self):
        return self.json_dicts # TODO make this into property

    def get_exemplar_name(self, json_path):
        """Find the exemplar sources string for the given ORACC JSON using its ../catalogue.json.
        Will be used to name the final docx.

        Eg. for rinap/rinap1/catalogue.json, text Q003414 has exemplars
            ZhArchSlg 1917 (+) ZhArchSlg 1918 (+) NA 12/76. The resulting DOCX
            for Q003414.json would then be
            "ZhArchSlg 1917 (+) ZhArchSlg 1918 (+) NA 12/76.docx"
        """
        if not self.catalogue_dict:
            print_if_verbose("Initializing catalogue dict")
            self._set_catalogue_json(json_path)

        try:
            q_number = os.path.basename(json_path).split(".json")[0]
            exemplar_name = self.catalogue_dict["members"][q_number]["exemplars"]

            # TODO: ignoring this for now
            # if "/" in exemplar_name:
            #     print("Exemplar name for textid {0} contains slash, escaping to || to avoid filesystem freakout".format(q_number))
            #     exemplar_name = exemplar_name.replace("/", "||")

            # if len(exemplar_name) > 240:
            #     print("Exemplar name for textid {0} is too long, truncating".format(q_number))
            #     exemplar_name = exemplar_name[:240] # 255 - 5 because of .docx in filename. Could still be too long for whole path tho :(
            # end TODO

            return exemplar_name
        except Exception as e:
            print("Unable to find exemplars for Q-number {0}. Reverting name to use Q-number.".format(q_number))
            return q_number

    def _set_catalogue_json(self, json_path):
        """Sets self.catalogue_dict by reading from json_path/../catalogue.json.
        """
        try:
            catalogue_path = os.path.join(os.path.dirname(json_path), "..", "catalogue.json")
            self.catalogue_dict = self._read_json_dict(catalogue_path)
        except Exception as e:
            print("Unable to find catalogue.json at {0}.".format(catalogue_path))

    def _read_json_dict(self, filename):
        with open(filename) as fd:
            raw_str = fd.read()
            return json.loads(raw_str)


class JsonParser(object):
    """
    Class to take in a local JSON file and output a docx.
    """
    def __init__(self, json_dict, output_directory):
        self.cdl_dict = json_dict
        self.output_directory = output_directory
        self.l_reflist = []  # for repeat nodes
        self.traversed_first_c_sentence_node = False  # TODO don't need this anymore if we're not using c-labels
        self.found_obverse_or_reverse_d_node = False  # trigger on first type=discourse c-node?

    def run(self):
        """Loads and parses given ORACC JSON, then saves the pieced-together
        text into a docx on disk.
        """
        textid = self.cdl_dict.get("textid", "")
        if not textid:
            print_if_verbose("Skipping malformed JSON from {0}:".format(self.cdl_dict["original_path"]))
            print_if_verbose(self.cdl_dict)
            return
        print_if_verbose(
            "Parsing textid {0} from project {1}".format(textid, self.cdl_dict["project"])
        )
        doc = Document()
        res = self.parse_json(doc)
        self.print_doc(doc)
        self.save_docx(doc)

    def parse_json(self, doc):
        """Walks through the JSON object and pieces together all the lemmas.
        No new sections like obverse/reverse yet. TODO complete docstring

        dict[cdl] is list
        dict[cdl][3] (or whatever index) has node == c; start parsing there
        dict[cdl][3][cdl] contains list of dicts with actual lemmas/line breaks
        """
        if not self.cdl_dict:
            return

        if self.cdl_dict["type"] != "cdl":
            print("Not a CDL-type JSON!\n")
            return

        # NOTE: was temporary, but now it'll stay
        # Add full exemplar name to the very top of docx
        p = doc.add_paragraph()
        p.add_run(self.cdl_dict["exemplars"])

        nodes = self.cdl_dict["cdl"]
        for c_node in nodes:
            chunk = c_node
            res = self.traverse_c_node(chunk, doc)

    def save_docx(self, doc):
        """Attempt to save the resulting docx file to current directory where
        script originally ran. Resulting docx will either be named after its
        Q-number textid or its exemplar sources.
        Args:
            #textid (str): ID of original JSON dict; basis of save name
                (eg. Q003456 -> Q003456.docx)
            doc (docx.Document): fully assembled docx object to be saved
        """
        try:
            docx_name = self._get_docx_name_to_save(self.cdl_dict["docx_name"]) + ".docx"
            docx_path = os.path.join(self.output_directory, docx_name)
            doc.save(docx_path)
            print("Saved docx in {0}".format(docx_path))
        except Exception as e:
            print("Couldn't save docx! {0}".format(e))

    def _get_docx_name_to_save(self, name):
        """Check if docx_name would be unique before saving. If not, append the appropriate
        number identifier. eg. "My Exemplar Name" -> "My Exemplar Name (1)", assuming
        "My Exemplar Name" exists.
        """
        number_id = 0
        original_name = name
        docx_name = name

        while True:
            if not os.path.exists(docx_name + ".docx"):
                return docx_name
            print("{0} exists, continuing".format(docx_name))
            number_id += 1
            docx_name = original_name + " ({0})".format(number_id)

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
            print_if_verbose(s)

        # Seeing if we're balanced or not
        print_if_verbose("[ count: {0}".format(full_left_brackets))
        print_if_verbose("] count: {0}".format(full_right_brackets))
        print_if_verbose("⸢ count: {0}".format(partial_left_brackets))
        print_if_verbose("⸣ count: {0}".format(partial_left_brackets))
        #assert(full_left_brackets == full_right_brackets) # TODO restore if you remove exemplar name
        #assert(partial_left_brackets == partial_right_brackets) # TODO ditto

    def traverse_c_node(self, c_dict, doc, first_c_node=False):
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

        # NOTE: If C node has a label, do we put it in? But it can be there if there's also
        # D-nodes already with eg. "Obverse"
        # if c_dict["type"] == "sentence" and "label" in c_dict:
        #     print_if_verbose("Looks like a sentence with a label, {0}".format(c_dict["label"]))
        #     if not self.traversed_first_c_sentence_node:
        #         print_if_verbose("Traversed my first C-node sentence!")
        #         self.traversed_first_c_sentence_node = True
        #     else:
        #         doc.add_paragraph()  # means this is after the first time, so extra newline needed
        #     p = doc.add_paragraph()
        #     p.add_run(c_dict["label"])

        # If we've reached the point of starting the actual text, ie. no D-nodes
        # with "obverse" or "reverse" have been encountered so far, we still need
        # some header, so we put in "Text"
        if c_dict["type"] == "discourse":
            if not self.found_obverse_or_reverse_d_node:
                p = doc.add_paragraph()
                p.add_run("Text")
                doc.add_paragraph()
                self.found_obverse_or_reverse_d_node = True

        for node in c_dict["cdl"]:
            if node["node"] == "c":
                self.traverse_c_node(node, doc, first_c_node=False)
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
          - excised
          - object
          - surface
          - tablet
          - punct
          - nonx/nonw
        """
        assert(d_dict["node"] == "d")
        d_type = d_dict["type"]

        if d_type == "line-start":
            # If there was eg. a lacuna before, don't insert a newline.
            # We want to keep a text flowing so that there's no empty lines
            # aside from before things like "Reverse"
            try:
                if not doc.paragraphs[-1].runs[-1].text:
                    print_if_verbose("Last line was empty, skipping line-start")
                    p = doc.add_paragraph()
            except Exception as e:
                print("Couldn't get last run before this line-start: {0}".format(e))
            # NOTE: disabled below since this was adding eg. custom line numbers that OCHRE won't be able to parse
            # Seems like custom header labels should come from C-nodes...? If at all?
            #p.add_run(d_dict.get("label", ""))  # eg. Inscription_A 1 in rinap4/Q003347

        elif d_type == "obverse":
            p = doc.add_paragraph()
            p.add_run("Obverse")
            doc.add_paragraph()
            self.found_obverse_or_reverse_d_node = True

        elif d_type == "reverse":
            # Needs extra newline before it, unlike obverse, since it comes later on in texts
            doc.add_paragraph()
            p = doc.add_paragraph()
            p.add_run("Reverse")
            doc.add_paragraph()
            self.found_obverse_or_reverse_d_node = True

        elif d_type == "punct":
            p = doc.paragraphs[-1]
            p.add_run(d_dict["frag"])
            p.add_run(d_dict.get("delim", ""))

        # Fuck this bit
        # Shitty sidestep for now: if starts with uppercase, assume logogram/non-italics (it's fine for rinap mostly)
        # If starts with lowercase, assume akkadian/italics
        elif d_type == "excised" and "frag" in d_dict: # TODO wip, can't do subscript/superscript convert, italics... need to parse per char
            self._add_excised_d_node(d_dict, doc)

        else:
            print_if_verbose("Unknown or noop d-value {0}".format(d_type))

    def _add_excised_d_node(self, d_dict, doc):
        """TODO Fuck this bit. Sidestepping for now (soln for which should work for now with RINAP):
        if first non-<</>> char is uppercase, assume entire blob Sumerian/logogram/non-italics
        If first non-<</>> char is lowercase, assume entire blob Akkadian/phonogram/italics
        Won't work with stuff in eg. SAAO/SAA16 CAMS that may have eg. [<<BU>>], <<BU>>], or {<<d}60. Fuck you CAMS/SAAO.
        Ideally, you'd tokenize everything in the middle of the <</>>'s and make them into eg. gdl_dicts
        to pass off to functions like _add_continuing_sign_form().
        """
        frag = d_dict["frag"].replace("<<", "«").replace("<", "‹").replace(">>", "»").replace(">", "›")
        #frag = self._convert_2_or_3_subscript(frag)
        stripped_frag = frag.strip("«").strip("»").strip("[")
        p = doc.add_paragraph()
        r = p.add_run(frag)

        if stripped_frag[0].islower(): # Seems like entire actual char portion of frag is Akkadian, make it all italic
            r.italic = True

        p.add_run(frag + d_dict["delim"])

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
        lang = l_dict["f"]["lang"]

        if lang == "arc":  # eg. Aramaic
            print_if_verbose("Adding Aramaic fragment")
            self._add_aramaic_frag(l_dict, last_paragraph)
            return
        elif lang == "qcu-949":  # seemingly English...
            print_if_verbose("Adding English fragment")
            self._add_english_frag(l_dict, last_paragraph)
            return
        elif lang != "akk":  # eg. sux for Sumerian
            print_if_verbose("Unrecognized language {0}".format(lang))

        gdl_list = l_dict["f"]["gdl"]

        for index in range(len(gdl_list)):
            node_dict = gdl_list[index]
            if "s" in node_dict:
                self._add_logogram(node_dict, last_paragraph)
            elif "v" in node_dict:
                self._add_continuing_sign_form(node_dict, last_paragraph)
            elif "det" in node_dict:
                # NOTE: if there's 2 determinatives stuck next to each other,
                # need to separate them with space or something else
                # since OCHRE will otherwise attempt to look up
                # eg. "md" instead of "m" and "d" dets separately
                try:
                    if "det" in gdl_list[index + 1]:
                        self._add_determinative(node_dict, last_paragraph, add_space_delim=True)
                    else:
                        self._add_determinative(node_dict, last_paragraph)
                except Exception as e:
                    print("Looks like a single determinative, not 2 stuck together! Exception: {0}".format(e))
            elif "gg" in node_dict:
                self._add_logogram_cluster(node_dict, last_paragraph)
            elif "x" in node_dict:
                self._add_ellipsis(node_dict, last_paragraph)
            elif "n" in node_dict:
                self._add_number(node_dict, last_paragraph)
            else:
                print_if_verbose("Unknown l-node {0}".format(node_dict))
        last_paragraph.add_run(l_dict["f"].get("delim", "")) # TODO still needed?

    def _add_aramaic_frag(self, l_node, paragraph):
        """Adds Aramaic fragment to current paragraph with all needed formatting.
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

    def _add_english_frag(self, l_node, paragraph):
        """Adds English fragment to current paragraph with all needed formatting.
        Example of English L node which this function will work on (in rinap/rinap4/corpusjson/Q003344.json):
        {
            "node": "l",
            "frag": "Horned",
            "id": "Q003344.l05b8e",
            "ref": "Q003344.3.1",
            "inst": "%qcu-949:*=",
            "f": {
              "lang": "qcu-949",
              "form": "*",
              "norm": "Horned"
            }
        }

        Args:
            l_node (dict): English lang node to be added
            paragraph (docx.text.paragraph.Paragraph): paragraph to add English fragment to
        """
        frag = l_node["frag"]
        paragraph.add_run(frag)
        paragraph.add_run(" ") # English nodes have no other default delim

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
        word = self._convert_2_or_3_subscript(gdl_node["v"])
        r = paragraph.add_run(word)
        if word.islower():
            r.italic = True
        print_if_verbose("Added continuing sign {0}".format(word))

        self._add_post_frag_symbols(gdl_node, paragraph)

    def _add_determinative(self, gdl_node, paragraph, add_space_delim=False):
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
        assert(gdl_node.get("det", "") == "semantic" or
               gdl_node.get("det", "") == "phonetic")

        if gdl_node["pos"] == "pre" or gdl_node["pos"] == "post":
            det_node = gdl_node["seq"][0]

            self._add_pre_frag_symbols(det_node, paragraph) # TODO document why det node

            # Add the determinative to paragraph with needed stylings
            det = det_node.get("s", det_node.get("v", ""))
            det = self._convert_2_or_3_subscript(det)
            r = paragraph.add_run(det)
            r.font.superscript = True
            print_if_verbose("Added determinative {0}".format(det))

            self._add_post_frag_symbols(det_node, paragraph)
            if add_space_delim:  # if there's another det right after this
                r = paragraph.add_run(".")  # TODO use . or space? Space looked a bit weird, so let's try .
                r.font.superscript = True
                print_if_verbose("Added extra . delim for double determinative")
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
        logogram = self._convert_2_or_3_subscript(gdl_node["s"])
        paragraph.add_run(logogram)
        print_if_verbose("Added logogram {0}".format(logogram))

        self._add_post_frag_symbols(gdl_node, paragraph)

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
            elif "v" in logo_dict:
                self._add_continuing_sign_form(logo_dict, paragraph)
            elif "n" in logo_dict:
                self._add_number(logo_dict, paragraph)
            elif "gg" in logo_dict:
                self._add_logogram_cluster(logo_dict, paragraph) # eg. for ligatures
            elif "x" in logo_dict:
                self._add_ellipsis(logo_dict, paragraph)
            else:
                print_if_verbose("Non-sign or determinative found in logogram cluster {0}".format(logo_dict))
        paragraph.add_run(gdl_node.get("delim", "")) # delim after the cluster

    def _add_ellipsis(self, gdl_node, paragraph):
        """Adds in things like (...), [...]
        """
        assert(gdl_node.get("x") == "ellipsis")

        self._add_pre_frag_symbols(gdl_node, paragraph)
        paragraph.add_run("...")
        self._add_post_frag_symbols(gdl_node, paragraph)

    def _add_number(self, gdl_node, paragraph):
        """Adds a number to current paragraph, eg. 4.
        """
        self._add_pre_frag_symbols(gdl_node, paragraph)
        paragraph.add_run(gdl_node["form"])
        self._add_post_frag_symbols(gdl_node, paragraph)

        print_if_verbose("Added number {0}".format(gdl_node["form"]))

    def _add_pre_frag_symbols(self, gdl_node, paragraph):
        """Adds any symbols that come before the actual text fragment.
        These chars may be added: [ ⸢ < <<
        Args:
            gdl_node (dict): dict of L(emma) node's "gdl" property TODO not for det!
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
            o_frag = o_frag.replace("<<", "«").replace("<", "‹").replace(">>", "»").replace(">", "›") # NOTE new
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
            r = paragraph.add_run("(?)")
            #r.font.superscript = True

        # Partial fragment break end
        if gdl_node.get("hc", ""):
            paragraph.add_run("⸣")

        # o for whatever reason may include [ or ], but this is already taken
        # care of by breakStart and breakEnd. Leave o to just be eg. ( ) < >>
        o_frag = gdl_node.get("o", "").strip("[]")
        if "id" in gdl_node and gdl_node.get("statusStart", "") == gdl_node["id"]:
            # o should already be a closer frag like ) or > or >>
            o_frag = o_frag.replace("<<", "«").replace("<", "‹").replace(">>", "»").replace(">", "›") # NOTE new
            paragraph.add_run(o_frag)

        # Full fragment break end
        if gdl_node.get("breakEnd", ""):
            paragraph.add_run("]")

        # Whatever delimiter follows, eg. - or space
        if gdl_node.get("delim", ""):
            paragraph.add_run(gdl_node["delim"])

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
        """Replaces h with ḫ, capital or lowercase.
        NOTE You don't need this, since OCHRE can auto sub in rocker-h for regular h
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
    parser = argparse.ArgumentParser(description='Parse your JSON here.')
    parser.add_argument('--file', '-f', required=True,
                        help='A path (file or directory) to the JSON file to parse into DOCX')
    parser.add_argument('--verbose', '-v', required=False, action="store_true",
                        help='Enable verbose mode during parsing')
    parser.add_argument('--use-exemplar', '-x', required=False, action="store_true",
                        help='Enable use of exemplar sources/citations as the name for final output instead of Q or P-number')
    parser.add_argument('--output-directory', '-o', required=False, action="store", default=".",
                        help="Specify directory to output result(s) to. This script will output to the current directory by default.")
    args = parser.parse_args()

    if args.verbose:
        global VERBOSE_FLAG
        VERBOSE_FLAG = True

    jl = JsonLoader(args.file, args.use_exemplar)
    for json_dict in jl.get_json_dicts():
        jp = JsonParser(json_dict, args.output_directory)
        jp.run()


if __name__ == "__main__":
    main()
