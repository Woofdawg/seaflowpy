import os
import sys

import click
from seaflowpy import beads
from seaflowpy import db
from seaflowpy import errors
from seaflowpy import seaflowfile
from seaflowpy import fileio
from seaflowpy import sample


def validate_file_fraction(ctx, param, value):
    if value <= 0 or value > 1:
        raise click.BadParameter(f'must be a number > 0 and <= 1.')
    return value


def validate_positive(ctx, param, value):
    if value is not None and value <= 0:
        raise click.BadParameter(f'must be a number > 0.')
    return value


def validate_seed(ctx, param, value):
    if value is not None and (value < 0 or value > (2**32 - 1)):
        raise click.BadParameter(f'must be between 0 and 2**32 - 1.')
    return value


@click.group()
def evt_cmd():
    """EVT file examination subcommand."""
    pass


@evt_cmd.command('count')
@click.option('-H', '--no-header', is_flag=True, default=False, show_default=True,
    help="Don't print column headers.")
@click.argument('evt-files', nargs=-1, type=click.Path(exists=True))
def count_evt_cmd(no_header, evt_files):
    """
    Reports event counts in EVT/OPP files.

    For speed, only a portion at the beginning of the file is read to get the
    event count. If any of EVT-FILES are directories all EVT/OPP files within
    those directories will be recursively found and examined. Files which can't
    be read with a valid EVT/OPP file name and file header will be reported
    with a count of 0.

    Unlike the "evt validate" command, this command does not attempt validation
    of the EVT/OPP file beyond reading the first 4 byte row count header.
    Because of this, there may be files where "evt validate" reports 0 rows
    while this tool reports > 0 rows.

    Outputs tab-delimited text to STDOUT.
    """
    if not evt_files:
        return

    # dirs to file paths
    files = expand_file_list(evt_files)

    header_printed = False

    for filepath in files:
        # Default values
        filetype = '-'
        file_id = '-'
        events = 0

        # Try to parse filename as SeaFlow file
        try:
            sff = seaflowfile.SeaFlowFile(filepath)
            file_id = sff.file_id
            if sff.is_opp:
                filetype = 'opp'
            else:
                filetype = 'evt'
        except errors.FileError:
            # Might have unusual name
            pass
        try:
            events = fileio.read_labview_row_count(filepath)
        except errors.FileError:
            pass  # accept defaults, do nothing

        if not header_printed and not no_header:
            print('\t'.join(['path', 'file_id', 'type', 'events']))
            header_printed = True
        print('\t'.join([filepath, file_id, filetype, str(events)]))


@evt_cmd.command('beads')
@click.option('-b', '--beads-evt-file', type=click.Path(exists=True), required=True,
    help='EVT file to use to locate beads.')
@click.option('-d', '--db', 'db_file', type=click.Path(exists=True), required=True,
    help='DB file to save filter parameters to. Should contain instrument serial number.')
@click.option('-e', '--evt-file', type=click.Path(exists=True),
    help='EVT file to use for final filtering diagnostic plots.')
@click.option('-f', '--frac', type=float, default=0.33, show_default=True,
    help='min_cluster_frac parameter to hdbscan. Min fraction of data which should be in cluster.')
@click.option('-o', '--other-params', type=click.Path(exists=True),
    help='Filtering parameter csv file to compare against')
@click.option('-p', '--plot', 'plot_file', type=click.Path(),
    help='Output file for bead finding diagnostic plots. PNG format.')
@click.option('-P', '--pe-min', type=int, default=40000, show_default=True,
    help='PE minimum cutoff to use during bead cluster detection.')
@click.option('-r', '--radius', type=int, callback=validate_positive,
    help='Radius of circle used to collect bead locations.')
def beads_evt_cmd(beads_evt_file, db_file, evt_file, frac, other_params,
                  plot_file, pe_min, radius):
    """
    Find bead location and generate filtering parameters.
    """
    # First get serial number from the database
    try:
        serial = db.get_serial(db_file)
    except errors.SeaFlowpyError as e:
        raise click.ClickException(e)

    click.echo("Finding beads for {}".format(db_file))
    try:
        results = beads.find_beads(beads_evt_file, serial, radius=radius,
                                   evt_path=evt_file, pe_min=pe_min,
                                   min_cluster_frac=frac)
    except (errors.SeaFlowpyError, ValueError) as e:
        raise click.ClickException(str(e))
    click.echo(results["filter_params"])

    if db_file:
        click.echo("Saving filter params to {}".format(db_file))
        try:
            vals = results["filter_params"].to_dict('index').values()
            db.save_filter_params(db_file, vals)
        except IOError as e:
            raise click.ClickException(str(e))

    if plot_file:
        click.echo("Generating image file {}".format(plot_file))
        try:
            if other_params:
                params = fileio.read_filter_params_csv(other_params)
                otherip = beads.params2ip(params)
            else:
                otherip = None
            beads.plot(results, plot_file, otherip=otherip)
        except IOError as e:
            raise click.ClickException(str(e))



@evt_cmd.command('sample')
@click.option('-o', '--outfile', type=click.Path(), required=True,
    help='Output file path. ".gz" extension will gzip output.')
@click.option('-c', '--count', type=int, default=100000, show_default=True, callback=validate_positive,
    help='Number of events to keep, before noise filtering.')
@click.option('-f', '--file-fraction', type=float, default=0.1, show_default=True, callback=validate_file_fraction,
    help='Fraction of files to sample from.')
@click.option('--min-chl', type=int, default=0, show_default=True,
    help='Mininum chlorophyll (small) value.')
@click.option('--min-fsc', type=int, default=0, show_default=True,
    help='Mininum forward scatter (small) value.')
@click.option('--min-pe', type=int, default=0, show_default=True,
    help='Mininum phycoerythrin value.')
@click.option('--min-date', type=str,
    help='Minimum date of file to sample.')
@click.option('--max-date', type=str,
    help='Maximum date of file to sample.')
@click.option('-n', '--noise-filter', 'filter_noise', is_flag=True, default=False, show_default=True,
    help='Apply noise filter before subsampling.')
@click.option('-s', '--seed', type=int, callback=validate_seed,
    help='Integer seed for PRNG, otherwise system-dependent source of randomness is used to seed the PRNG.')
@click.option('-v', '--verbose', count=True,
    help='Show more information. Specify more than once to show more information.')
@click.argument('files', nargs=-1, type=click.Path(exists=True))
def sample_evt_cmd(outfile, count, file_fraction, min_chl, min_fsc, min_pe,
                   min_date, max_date, filter_noise, seed, verbose, files):
    """
    Sample a subset of rows in EVT files.

    The list of EVT files can be file paths or directory paths
    which will be searched for EVT files.
    COUNT events will be randomly selected from all data.
    For speed, only a fraction of the files will be sampled from,
    specified by FILE-FRACTION.
    """
    # dirs to file paths, only keep EVT/OPP files
    files = seaflowfile.keep_evt_files(expand_file_list(files))
    files = seaflowfile.timeselect_evt_files(files, min_date, max_date)
    try:
        df = sample.sample(
            files, count, file_fraction, filter_noise=filter_noise,
            min_chl=min_chl, min_fsc=min_fsc, min_pe=min_pe, seed=seed,
            verbose=verbose
        )
    except (ValueError, IOError) as e:
        raise click.ClickException(str(e))
    try:
        fileio.write_labview(df, outfile)
    except (IOError, OSError) as e:
        raise click.ClickException("Could not write output file: {}".format(str(e)))


@evt_cmd.command('validate')
@click.option('-a', '--all', 'report_all', is_flag=True,
    help='Show information for all files. If not specified then only files errors are printed.')
@click.argument('files', nargs=-1, type=click.Path(exists=True))
def validate_evt_cmd(report_all, files):
    """
    Examines EVT/OPP files.

    If any of the file arguments are directories all EVT/OPP files within those
    directories will be recursively found and examined. Prints file validation
    report to STDOUT. Print summary of files passing validation to STDERR.
    """
    if not files:
        return

    # dirs to file paths
    files = expand_file_list(files)

    header_printed = False
    ok, bad = 0, 0

    for filepath in files:
        # Default values
        type_from_filename = '-'
        filetype = '-'
        file_id = '-'
        events = 0

        # Try to parse filename as SeaFlow file
        try:
            sff = seaflowfile.SeaFlowFile(filepath)
            file_id = sff.file_id
            if sff.is_evt:
                type_from_filename = 'evt'
                filetype = 'evt'
            elif sff.is_opp:
                type_from_filename = 'opp'
                filetype = 'opp'
        except errors.FileError:
            # unusual name, no file_id
            pass

        if type_from_filename == 'evt':
            try:
                data = fileio.read_evt_labview(filepath)
                status = 'OK'
                ok += 1
                events = len(data.index)
            except errors.FileError as e:
                status = str(e)
                bad += 1
                events = 0
        elif type_from_filename == 'opp':
            try:
                data = fileio.read_opp_labview(filepath)
                status = 'OK'
                ok += 1
                events = len(data.index)
            except errors.FileError as e:
                status = str(e)
                bad += 1
                events = 0
        elif type_from_filename == '-':
            # Try to read as both EVT or OPP
            try:
                data = fileio.read_evt_labview(filepath)
                filetype = 'evt'
                status = 'OK'
                ok += 1
                events = len(data.index)
            except errors.FileError:
                try:
                    data = fileio.read_opp_labview(filepath)
                    filetype = 'opp'
                    status = 'OK'
                    ok += 1
                    events = len(data.index)
                except errors.FileError as e:
                    status = str(e)
                    bad += 1
                    events = 0

        if not header_printed:
            print('\t'.join(['path', 'file_id', 'type', 'status', 'events']))
            header_printed = True
        if (report_all and status == 'OK') or (status != 'OK'):
            print('\t'.join([filepath, file_id, filetype, status, str(events)]))
    print('%d/%d files passed validation' % (ok, bad + ok), file=sys.stderr)


def expand_file_list(files_and_dirs):
    """Convert directories in file list to EVT/OPP file paths."""
    # Find files in directories
    dirs = [f for f in files_and_dirs if os.path.isdir(f)]
    files = [f for f in files_and_dirs if os.path.isfile(f)]

    dfiles = []
    for d in dirs:
        evt_files = seaflowfile.find_evt_files(d)
        opp_files = seaflowfile.find_evt_files(d, opp=True)
        dfiles = dfiles + evt_files + opp_files

    return files + dfiles
