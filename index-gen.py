#!/usr/bin/env python
import json
import os
import argparse

from docx import Document

"""Tool to generate a flat file with metadata of files for use with autokey.
Each entry contains:
- Q, X, or P-number (textid; to be used as English title)
- absolute path to docx file
- size (or # of lines) of file
- museum/popular/primary name (to be used as an alias)
- other exemplar/museum info (to be used in description)

NOTE: will not render unicode on output, but seems to paste just fine...
"""

# These contain your corpusjson folders as well as catalogue.json
# Your docx folder is also expected to have this folder structure
folders = [
    'ribo/babylon6',
    'ribo/babylon7',
    'ribo/babylon8',
    'rinap/rinap1',
    'rinap/rinap3',
    'rinap/rinap4',
    'saao/saa01',
    'saao/saa05',
    'saao/saa11',
    'saao/saa15',
    'saao/saa16',
    'saao/saa17',
    'saao/saa18',
    'saao/saa19',
    'suhu'
]

def _read_catalogue(json_path):
    with open(json_path) as fd:
        return json.load(fd)

def _save_catalogue(my_catalogue, json_path):
    with open(json_path, 'w+') as outfile:
        json.dump(my_catalogue, outfile, sort_keys=True, indent=4)

def create_flat_files(oracc_path, docx_parent_path):
    """Output some JSONs... we'll see how we want to format them later
    """
    for folder in folders:
        print(folder)
        my_catalogue = {}

        # Parse catalogue JSON
        catalogue_path = os.path.join(oracc_path, folder, "catalogue.json")
        catalogue_dict = _read_catalogue(catalogue_path)

        members = catalogue_dict["members"]

        for textid in members:
            # Check if it's got a docx equivalent
            # If not, don't bother adding it to my catalogue
            print(textid)
            docx_name = textid + ".docx"
            docx_path = os.path.join(docx_parent_path, folder, docx_name)
            if not os.path.exists(docx_path):
                continue

            # Count # of lines present
            document = Document(docx_path)
            n_lines = len(document.paragraphs)

            text_info = members[textid]

            if "rinap" in folder:
                my_catalogue.update({
                    textid: {
                        "docx_path": docx_path,
                        "docx_lines": n_lines,
                        "ochre_title": textid,
                        "alias": text_info["popular_name"],
                    },
                })
                if "collection" in text_info or "exemplars" in text_info:
                    my_catalogue[textid].update({
                        "description": "Collection:\n{0}\nExemplars:\n{1}".format(
                            text_info.get("collection", ""),
                            text_info.get("exemplars", "")
                        ),
                    })

            elif "ribo" in folder:
                my_catalogue.update({
                    textid: {
                        "docx_path": docx_path,
                        "docx_lines": n_lines,
                        "ochre_title": textid,
                        "alias": text_info["popular_name"],
                    },
                })
                if "collection" in text_info or "exemplars" in text_info:
                    my_catalogue[textid].update({
                        "description": "Collection:\n{0}\nExemplars:\n{1}".format(
                            text_info.get("collection", ""),
                            text_info.get("exemplars", "")
                        ),
                    })

            elif "saao" in folder:
                my_catalogue.update({
                    textid: {
                        "docx_path": docx_path,
                        "docx_lines": n_lines,
                        "ochre_title": textid,
                        "alias": text_info.get("museum_no", text_info["display_name"]),
                        "description": "Primary publication exemplars:\n{0}".format(
                            text_info["primary_publication"]
                        ),
                    },
                })

            else: # suhu
                if "museum_no" not in text_info:
                    print("no museum_no in ^")
                my_catalogue.update({
                    textid: {
                        "docx_path": docx_path,
                        "docx_lines": n_lines,
                        "ochre_title": textid,
                        "alias": text_info.get("museum_no", text_info["popular_name"]),
                    },
                })
                if "collection" in text_info:
                    my_catalogue[textid].update({
                        "description": "Collection:\n{0}".format(
                            text_info.get("collection", "")
                        ),
                    })

        # Save to file in docx folders
        _save_catalogue(my_catalogue, os.path.join(docx_parent_path, folder, "my-catalogue.json"))


def main():
    parser = argparse.ArgumentParser(
        description="Generates a flat file containing metadata to use with autokey OCHRE input scripts.")

    parser.add_argument(
        '--oracc-path',
        '-p',
        action="store",
        help="Path to your ORACC JSON git directory (a copy of the untarred contents of https://github.com/oracc/json)",
        required=True,
        type=str,
    )
    parser.add_argument(
        '--docx-path',
        '-o',
        action="store",
        help="Path to your DOCX directory",
        required=True,
        type=str,
    )

    args = parser.parse_args()
    oracc_path = os.path.abspath(args.oracc_path)
    docx_path = os.path.abspath(args.docx_path)

    create_flat_files(oracc_path, docx_path)


if __name__ == "__main__":
    main()