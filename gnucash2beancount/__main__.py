import argparse

import gnucash
from . import converter
from . import printer


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('gnucash_path')
    parser.add_argument('beancount_path')
    parser.add_argument('--currency', default='USD')
    return parser.parse_args()


def main():
    args = parse_args()

    print('Opening GnuCash file...')
    with gnucash.Session(
            args.gnucash_path,
            gnucash.SessionOpenMode.SESSION_NORMAL_OPEN) as sess:
        gnc_converter = converter.Converter(sess.get_book())
        print('Start conversion...')
        entries = gnc_converter.convert(currency=args.currency)
    with open(args.beancount_path, 'w') as outfile:
        printer.print_entries(entries, file=outfile)
    print('Done!')


if __name__ == '__main__':
    main()
