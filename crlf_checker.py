import sys
from glob import glob

from chardet.universaldetector import UniversalDetector


def analyze_line_ending(filename):
    detector = UniversalDetector()

    with open(filename, "rb") as f:
        for line in f:
            detector.feed(line)
            if detector.done:
                detector.close()
                break

    if detector.result["encoding"] == "UTF-16":
        encoding = "utf-16-le"
    elif detector.result["encoding"] is None:
        encoding = "latin-1"
    else:
        encoding = detector.result["encoding"]

    with open(filename, encoding=encoding, newline="") as f:
        lines = f.readlines()
        crlf_count = 0
        lf_count = 0
        for line in lines:
            if line[-1] != "\n":
                continue
            elif len(line) >= 2:
                if line[-2:] == "\r\n":
                    crlf_count += 1
                else:
                    lf_count += 1

    return {
        "mixed": crlf_count > 0 and lf_count > 0,
        "crlf_count": crlf_count,
        "lf_count": lf_count,
    }


if len(sys.argv) < 2:
    print(f"Usage: python {sys.argv[0]} <mod_directory>")
    exit(1)
txt_files = glob(f"{sys.argv[1]}/**/*.txt", recursive=True)
mixed_count = 0
print("CRLF  \tLF    \tFILENAME")
print("------\t------\t-----------------------------")
for file in txt_files:
    mixed_result = analyze_line_ending(file)
    if mixed_result["mixed"]:
        print(f'{mixed_result["crlf_count"]:<6}\t{mixed_result["lf_count"]:<6}\t{file}')
        mixed_count += 1
if mixed_count > 0:
    print()
print(f"{mixed_count} mixed line-ending txt files found.")
