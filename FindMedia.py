import config
import logging
import os
import unidecode
import sys
from plexapi.server import PlexServer
from logging.handlers import RotatingFileHandler

log_file, file_extension = os.path.splitext(os.path.basename(__file__))
formatter = logging.Formatter('%(asctime)s - %(levelname)10s - %(module)15s:%(funcName)30s:%(lineno)5s - %(message)s')
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
logging.getLogger("requests").setLevel(logging.WARNING)
logger.setLevel(config.log_level.upper())
fileHandler = RotatingFileHandler(config.log_folder + '/' + log_file + '.log', maxBytes=1024 * 1024 * 1, backupCount=1)
fileHandler.setFormatter(formatter)
logger.addHandler(fileHandler)

plex_server = PlexServer(config.plex_host, config.plex_api)


def find_missing_from_db(medias_from_file_system, medias_from_db):
    logger.debug('Finding items missing from Database')
    missing_from_db = []
    try:
        # mediasFromFileSystem
        for item in medias_from_file_system:
            if item not in medias_from_db:
                missing_from_db.append(item)
        return missing_from_db
    except ValueError:
        logger.error('Aborted in findMissingFromDB')


def find_missing_from_fs(medias_from_file_system, medias_from_db):
    logger.debug('Finding items missing from FileSystem')
    missing_from_fs = []
    try:
        for item in medias_from_db:
            if item not in medias_from_file_system:
                missing_from_fs.append(item)
        return missing_from_fs
    except ValueError:
        logger.error('Aborted in findMissingFromFS')


def add_this_item(filename):
    try:
        if os.path.splitext(filename)[1].lower()[1:] in config.DEFAULT_PREFS['VALID_EXTENSIONS']:
            parts = split_all(filename)
            for part in parts:
                if config.DEFAULT_PREFS['IGNORE_EXTRAS']:
                    if part.lower() in config.ExtrasDirs:
                        return False
                    for extra in config.Extras:
                        if extra in part.lower():
                            return False
                if config.DEFAULT_PREFS['IGNORE_SPECIALS']:
                    for special in config.Specials:
                        if special == part.lower():
                            return False
                if config.DEFAULT_PREFS['IGNORE_HIDDEN']:
                    if part.startswith('.'):
                        return False
            return True
        else:
            return False
    except Exception as e:
        logger.error('Exception in addThisItem was %s' % e)
        return False


def split_all(path):
    allparts = []
    while 1:
        parts = os.path.split(path)
        if parts[0] == path:
            allparts.insert(0, parts[0])
            break
        elif parts[1] == path:
            allparts.insert(0, parts[1])
            break
        else:
            path = parts[0]
            allparts.insert(0, parts[1])
    return allparts


def get_files(file_path):
    try:
        medias_from_file_system = []
        scan_status_count = 0
        file_count = 0
        for Path in file_path:
            scan_status_count += 1
            logger.info("Scanning filepath #%s: %s" % (scan_status_count, Path))
            try:
                for root, subdirs, files in os.walk(Path.replace(config.remote_path_remote, config.remote_path_local)):
                    for filename in files:
                        filename_adjusted = os.path.join(root, filename)
                        if add_this_item(filename_adjusted):
                            file_count += 1
                            filename_original = filename_adjusted.replace(config.remote_path_local, config.remote_path_remote)
                            logger.debug('appending file: %s' % filename_original)
                            medias_from_file_system.append(unidecode.unidecode(filename_original))
            except Exception as e:
                logger.error('Exception happened in FM scanning filesystem: %s' % e)
        logger.info('Finished scanning filesystem - %s Files Found' % file_count)

        return medias_from_file_system
    except Exception as e:
        logger.error('Exception happened in getFiles: %s' % e)


def plex_files(section_id, section_type):
    logger.info("Scanning Plex Section Id: %s, Section Type: %s" % (section_id, section_type))
    plex_section = plex_server.library.sectionByID(section_id)
    plex_items = []
    if section_type == 'movie':
        plex_items = plex_section.search()
    elif section_type == 'show':
        plex_items = plex_section.searchEpisodes()

    filenames = []
    for item in plex_items:
        filenames += plex_to_filename(item)
    return filenames


def plex_to_filename(item):
    patched_items = []
    for zomg in item.media:
        zomg._initpath = item.key
        patched_items.append(zomg)

    zipped = zip(patched_items, item.iterParts())
    parts = sorted(zipped, key=lambda i: i[1].size if i[1].size else 0, reverse=True)
    filenames = [unidecode.unidecode(video.file) for media, video in parts]
    return filenames


def scan_medias(section_number, section_locations, section_type):
    try:
        medias_from_db = []

        if section_type == 'movie' or section_type == 'show':
            medias_from_db = plex_files(section_number, section_type)
        else:
            logger.info('Unsupported Section Type: %s' % section_type)
        medias_from_file_system = get_files(section_locations)

        missing_from_fs = find_missing_from_fs(medias_from_file_system, medias_from_db)
        missing_from_db = find_missing_from_db(medias_from_file_system, medias_from_db)

        logger.debug(
            "Files Missing from the File System for Section Number: %s: %s" % (section_number, len(missing_from_fs)))
        logger.debug("Files Missing from Plex for Section Number: %s: %s" % (section_number, len(missing_from_db)))
        return missing_from_fs, missing_from_db
    except Exception as e:
        logger.error('Exception happened in scanMedias: %s' % e)


if __name__ == "__main__":
    logger.info('scanSection started')
    error = False
    review = ""
    try:
        missing_files = []
        missing_db = []
        MissingFromFS = []
        MissingFromDB = []
        sectionNumber = '1'
        sectionLocations = '/mnt/Movies'
        sectionType = 'movie'
        plex_sections = plex_server.library.sections()
        for section in plex_sections:
            sectionNumber = section.key
            sectionTitle = section.title
            sectionType = section.type
            sectionLocations = section.locations

            logger.info('Going to scan section %s with a title of %s and a type of %s and locations as %s' % (sectionNumber, sectionTitle, sectionType, str(sectionLocations)))
            (MissingFromFS, MissingFromDB) = scan_medias(sectionNumber, sectionLocations, sectionType)
            missing_files += MissingFromFS
            missing_db += MissingFromDB

        message = ""
        if len(MissingFromFS + MissingFromDB) > config.error_threshold:
            message = message + "Over Threshold of %s Files Missing. Check Server" % config.error_threshold
        else:
            if not len(missing_files):
                message = message + "***Files Missing From File System***\n"
                for file in missing_files:
                    message = message + file + '\n'
            if not len(missing_db):
                message = message + "***Files Missing From Plex***\n"
                for file in missing_db:
                    message = message + file + '\n'

        if not len(message):
            review = "%s Files Missing from FS, %s Files Missing from Plex" % (len(missing_files), len(missing_db))
            logger.error("%s Files Missing from FS, %s Files Missing from Plex" % (len(missing_files), len(missing_db)))
            if len(missing_files):
                logger.error("Files Missing from the File System: %s" % missing_files)
            if len(missing_db):
                logger.error("Files Missing from Plex: %s" % missing_db)
        else:
            logger.info("No Files Missing")

    except Exception as ex:
        logger.error('Fatal error happened in scanSection: %s' % ex)
