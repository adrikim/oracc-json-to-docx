#!/usr/bin/env python
import json
import os
import sys
import argparse

"""Tool to generate a flat file with metadata of files for use with autokey.
Each entry contains:
- Q, X, or P-number (textid; to be used as English title)
- absolute path to docx file
- size (or # of lines) of file // obsolete if we can do image matches!
- museum/common name (to be used as an alias)
- other exemplar/museum info (to be used in description)
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

def create_flat_files(oracc_path, docx_parent_path):
    """Output some JSONs... we'll see how we want to format them later
    museum/common_title museum/exemplar_info

    Relevant info from each project:
    RINAP:
    display_name, eg. RINAP 4 001
    primary_publication/designation, eg. Esarhaddon 001 *
    collection, eg. British Museum, London, UK; Oriental Institute...
    exemplars, eg. BM 121005 (0001); K 0123 + K 0234; ...
    popular_name, eg. K 13733

    RIBO:
    display_name, eg. RINAP 4 104
    primary_publication/designation, eg. Esarhaddon 104
    exemplars, eg. BM 09876 (Bu 18888-05-02), ...
    collection, eg. British Museum, London, UK; ...
    popular_name, eg. Babylon A

    SAAO:
    museum_no, eg. IM 34567
    primary_publication, eg. NL 986; ND 2345; ...
    designation/display_name, eg. SAA 01 001

    SUHU:
    primary_publication/designation, eg. Ninurta-kudurri-usur 01
    collection, eg. Iraq Museum, Baghdad, Iraq
    museum_no, eg. possibly IM 090909; IM 123458; IM -
    popular_name, eg. RIMB 2 S.0.1002.1
    """
    for folder in folders:
        my_catalogue = {}

        # Parse catalogue JSON
        catalogue_path = os.path.join(folder, "catalogue.json")
        catalogue_dict = _read_catalogue(catalogue_path)

        members = catalogue_dict["members"]

        for textid in members:
            # Check if it's got a docx equivalent
            # If not, don't bother adding it to my catalogue
            docx_name = textid + ".docx"
            docx_path = os.path.join(docx_parent_path, folder, docx_name)
            if not os.path.exists(docx_path):
                continue

            my_catalogue.update({
                textid: {
                    "docx_path": docx_path,
                    "ochre_title": textid,
                    "abbreviation": None,
                    "alias": None,
                    "museum_info": None
                },
            })

        # Save to file in docx folders


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