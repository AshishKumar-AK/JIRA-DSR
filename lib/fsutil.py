import glob
import os
import re
import time
import datetime
import dateutil.relativedelta
import shutil
import gzip


class FSUtil:
    """
    Custom utility class to handle file system related operations
    """
    @staticmethod
    def rotate_files(_dir, file_pattern, backup_count=0, backup_period='7d', archive=False):
        """
        This purpose of this method is rotate files within a directory which are older
        than certain period i.e.( 7 days: 7d or 2 Months: 2m).

        This method identifies files which should be rotated based on their shell glob name
        pattern passed to file_pattern parameter.

        if archive parameter is set to true then all files which have been qualified for
        rotation based on their modification date will be compressed and archived but not deleted.

        If set to False (default) then all files which are older than backup_period will
        be deleted.

        you can also restrict the number of rotated archived file which should be kept.

        :param _dir: (string) path to directory where files should be rotated
        :param file_pattern: (glob pattern) pattern of file names which should be rotated
        :param backup_count: (int) no. of rotated files which should be kept in backup.
        If 0 then all the rotated files are kept.
        :param backup_period: (string) how much older file should be eligible for rotation
        :param archive: bool True if rotated files should be archived.
        :return: None
        """
        mapping = dict(y='years', m='months', w='weeks',
                       d='days', h='hours', i='minutes', s='seconds')
        regex = '^(\d+)([ymwdhis])'
        match = re.compile(regex, re.IGNORECASE).match(backup_period).groups()
        if not os.path.exists(_dir):
            raise ValueError("Input directory does not exists!")
        if match is None or not match:
            raise ValueError('''backup_period parameter is not valid!
            Allowed values are: digits[ymwdhis]
            WHERE {}'''.format(mapping))
        if not isinstance(archive, bool):
            raise ValueError("archive parameter is not boolean")
        if not isinstance(backup_count, int):
            raise ValueError("backup_count parameter is not integer")
        else:
            digit, unit = match
            m = {mapping.get(str(unit).lower()): int(digit)}
            period = time.mktime((datetime.datetime.now()-dateutil.relativedelta.relativedelta(**m))
                                 .timetuple())*1000
            all_files = glob.glob(os.path.join(_dir, file_pattern))
            files = {file: os.path.getmtime(file)*1000 for file in all_files
                     if os.path.getmtime(file)*1000 >= period}
            backup_count = backup_count if backup_count else len(files)
            shorted_files = dict(sorted(files.items(), key=lambda x: x[1],
                                        reverse=True)[:backup_count])
            file_list = (file if file in shorted_files else os.unlink(file)
                         for file in all_files)
            for file in file_list:
                if archive:
                    with open(file, 'rb') as f_in:
                        with gzip.open(file+".gz", 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                    os.unlink(file)

    @staticmethod
    def copy_file(src, dst, metadata=False):
        """
        This method copies source file to a new file.
        This method also handles copying of symlinks source files

        :param src: (string) source file path
        :param dst: (string) dest file path
        :param metadata: bool True if source file permission
        attributes should also be copied to destination file
        :return: None
        """
        if os.path.islink(src):
            symlink = os.readlink(src)
            if os.path.exists(dst):
                os.unlink(dst)
            os.symlink(symlink, dst)
        else:
            shutil.copy2(src, dst) if metadata else shutil.copy(src, dst)

    @staticmethod
    def copy_dir(src, dst, metadata=False):
        """
        This method copies content of source directory to a destination directory.
        This method also creates destination directory if it does not exist.

        :param src: (string) source dir
        :param dst: (string) destination dir
        :param metadata: bool True if directory permission
        attributes should also be copied to destination dir
        :return: None
        """
        if not os.path.exists(dst):
            os.mkdir(dst)
            if metadata:
                shutil.copystat(src, dst)
        root, dirs, files = os.walk(src).__next__()
        if files:
            _ = all(map(lambda f: FSUtil.copy_file(os.path.join(root, f),
                                                   os.path.join(dst, f), metadata), files))
        if dirs:
            _ = all(map(lambda d: FSUtil.copy_dir(os.path.join(root, d),
                                                  os.path.join(dst, d), metadata), dirs))

    @staticmethod
    def replace_text_in_file(file, search_exp, replace_exp, original_bkp=False):
        """
        This method replaces any string pattern to different string within a text file.

        :param file: (string) path of file in which text to be replaced
        :param search_exp: (regex pattern) of source string to be replaced
        :param replace_exp: (regex pattern) of target string to be replaced with
        :param original_bkp: bool True if an unmodified version of original file should
        be kept as backup with '.bkp' extension
        :return: None
        """
        import fileinput
        import re
        with fileinput.input(file, inplace=original_bkp, backup='.bkp') as f:
            for line in f:
                line = re.sub(search_exp, replace_exp, line.rstrip())
                print(line)