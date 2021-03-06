#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Copyright (c) 2020 Colin Curtain

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
THE SOFTWARE.

Author: Colin Curtain (ccbogel)
https://github.com/ccbogel/QualCoder
https://qualcoder.wordpress.com/
"""

import configparser
import datetime
import gettext
import json  # to get latest release
import logging
from logging.handlers import RotatingFileHandler
import os
import platform
import shutil
import sys
import sqlite3
import traceback
import urllib.request
import webbrowser

from PyQt5 import QtCore, QtGui, QtWidgets

from attributes import DialogManageAttributes
from cases import DialogCases
from codebook import Codebook
from code_text import DialogCodeText
from copy import copy
from dialog_sql import DialogSQL
from GUI.ui_main import Ui_MainWindow
from import_survey import DialogImportSurvey
from information import DialogInformation
from journals import DialogJournals
from manage_files import DialogManageFiles
from memo import DialogMemo
from refi import Refi_export, Refi_import
from reports import DialogReportCodes, DialogReportCoderComparisons, DialogReportCodeFrequencies
from report_relations import DialogReportRelations
from rqda import Rqda_import
from settings import DialogSettings
#from text_mining import DialogTextMining
from view_av import DialogCodeAV
from view_graph_original import ViewGraphOriginal
from view_image import DialogCodeImage

qualcoder_version = "QualCoder 2.1"

path = os.path.abspath(os.path.dirname(__file__))
home = os.path.expanduser('~')
if not os.path.exists(home + '/.qualcoder'):
    try:
        os.mkdir(home + '/.qualcoder')
    except Exception as e:
        print("Cannot add .qualcoder folder to home directory\n" + str(e))
        raise
logfile = home + '/.qualcoder/QualCoder.log'
# Hack for Windows 10 PermissionError that stops the rotating file handler, will produce massive files.
try:
    f = open(logfile, "r")
    data = f.read()
    f.close()
    if len(data) > 12000:
        os.remove(logfile)
        f.open(logfile, "w")
        f.write(data[10000:])
        f.close()
except Exception as e:
    print(e)
logging.basicConfig(format='%(asctime)s %(levelname)s %(name)s.%(funcName)s %(message)s',
     datefmt='%Y/%m/%d %H:%M:%S', filename=logfile)
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
# The rotating file handler does not work on Windows
handler = RotatingFileHandler(logfile, maxBytes=4000, backupCount=2)
logger.addHandler(handler)

def exception_handler(exception_type, value, tb_obj):
    """ Global exception handler useful in GUIs.
    tb_obj: exception.__traceback__ """
    tb = '\n'.join(traceback.format_tb(tb_obj))
    text = 'Traceback (most recent call last):\n' + tb + '\n' + exception_type.__name__ + ': ' + str(value)
    print(text)
    logger.error(_("Uncaught exception : ") + text)
    mb = QtWidgets.QMessageBox()
    mb.setStyleSheet("* {font-size: 10pt}")
    mb.setWindowTitle(_('Uncaught Exception'))
    mb.setText(text)
    mb.exec_()


class App(object):
    """ General methods for loading settings and recent project stored in .qualcoder folder.
    Savable settings does not contain project name, project path or db connection.
    """

    version = qualcoder_version
    conn = None
    project_path = ""
    project_name = ""
    # Can delete the most current back up if the project has not been altered
    delete_backup_path_name = ""
    delete_backup = True
    # Used as a default export location, which may be different from the working directory
    last_export_directory = ""

    def __init__(self):
        sys.excepthook = exception_handler
        self.conn = None
        self.project_path = ""
        self.project_name = ""
        self.last_export_directory = ""
        self.delete_backup = True
        self.delete_backup_path_name = ""
        self.confighome = os.path.expanduser('~/.qualcoder')
        self.configpath = os.path.join(self.confighome, 'config.ini')
        self.persist_path = os.path.join(self.confighome, 'recent_projects.txt')
        self.settings = self.load_settings()
        self.last_export_directory = copy(self.settings['directory'])
        self.version = qualcoder_version

    def read_previous_project_paths(self):
        """ Recent project paths are stored in .qualcoder/recent_projects.txt
        Remove paths that no longer exist.
        Moving from only listing the previous project path to: date opened | previous project path.
        Write a new file in order of most recent opened to older and without duplicate projects.
        """

        previous = []
        try:
            with open(self.persist_path, 'r') as f:
                for line in f:
                    previous.append(line.strip())
        except:
            logger.info('No previous projects found')

        # Add paths that exist
        interim_result = []
        for p in previous:
            splt = p.split("|")
            proj_path = ""
            if len(splt) == 1:
                proj_path = splt[0]
            if len(splt) == 2:
                proj_path = splt[1]
            if os.path.exists(proj_path):
                interim_result.append(p)

        # Remove duplicate project names, keep the most recent
        interim_result.sort(reverse=True)
        result = []
        proj_paths = []
        for i in interim_result:
            splt = i.split("|")
            proj_path = ""
            if len(splt) == 1:
                proj_path = splt[0]
            if len(splt) == 2:
                proj_path = splt[1]
            if proj_path not in proj_paths:
                proj_paths.append(proj_path)
                result.append(i)

        # Write the latest projects file in order of most recently opened and without duplicate projects
        with open(self.persist_path, 'w') as f:
            for i, line in enumerate(result):
                f.write(line)
                f.write(os.linesep)
                if i > 8:
                    break
        return result

    def append_recent_project(self, path):
        """ Add project path as first entry to .qualcoder/recent_projects.txt
        """

        if path == "":
            return
        nowdate = datetime.datetime.now().astimezone().strftime("%Y-%m-%d_%H:%M:%S")
        result = self.read_previous_project_paths()
        dated_path = nowdate + "|" + path
        if result == []:
            print("Writing to", self.persist_path)
            with open(self.persist_path, 'w') as f:
                f.write(dated_path)
                f.write(os.linesep)
            return

        proj_path = ""
        splt = result[0].split("|") #open_menu
        if len(splt) == 1:
            proj_path = splt[0]
        if len(splt) == 2:
            proj_path = splt[1]
        #print("PATH:", path, "PPATH:", proj_path)  # tmp
        if path != proj_path:
            result.append(dated_path)
            result.sort()
            with open(self.persist_path, 'w') as f:
                for i, line in enumerate(result):
                    f.write(line)
                    f.write(os.linesep)
                    if i > 8:
                        break

    def get_most_recent_projectpath(self):
        """ Get most recent project path from .qualcoder/recent_projects.txt """

        result = self.read_previous_project_paths()
        if result:
            return result[0]

    def create_connection(self, project_path):
        """ Create connection to recent project and load codes, categories and model """

        self.project_path = project_path
        self.project_name = project_path.split('/')[-1]
        self.conn = sqlite3.connect(os.path.join(project_path, 'data.qda'))

    def get_code_names(self):
        cur = self.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        res = []
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_filenames(self):
        """ Get all filenames. As id, name """
        cur = self.conn.cursor()
        cur.execute("select id, name from source order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_casenames(self):
        """ Get all casenames. As id, name """
        cur = self.conn.cursor()
        cur.execute("select caseid, name from cases order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_text_filenames(self):
        """ Get filenames of textfiles only. """
        cur = self.conn.cursor()
        cur.execute("select id, name from source where mediapath is Null order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_image_filenames(self):
        """ Get filenames of image files only. """
        cur = self.conn.cursor()
        cur.execute("select id, name from source where mediapath like '/images/%' order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_av_filenames(self):
        """ Get filenames of audio video files only. """
        cur = self.conn.cursor()
        cur.execute("select id, name from source where (mediapath like '/audio/%' or mediapath like '/video/%') order by lower(name)")
        result = cur.fetchall()
        res = []
        for row in result:
            res.append({'id': row[0], 'name': row[1]})
        return res

    def get_annotations(self):
        """ Get annotations for text files. """

        cur = self.conn.cursor()
        cur.execute("select anid, fid, pos0, pos1, memo, owner, date from annotation where owner=?",
            [self.settings['codername'], ])
        result = cur.fetchall()
        res = []
        keys = 'anid', 'fid', 'pos0', 'pos1', 'memo', 'owner', 'date'
        for row in result:
            res.append(dict(zip(keys, row)))
        return res

    def get_data(self):
        """ Called from init and gets all the codes, categories.
        Called from code_text, code_av, code_image, reports, report_crossovers """

        categories = []
        cur = self.conn.cursor()
        cur.execute("select name, catid, owner, date, memo, supercatid from code_cat order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'catid', 'owner', 'date', 'memo', 'supercatid'
        for row in result:
            categories.append(dict(zip(keys, row)))
        codes = []
        cur = self.conn.cursor()
        cur.execute("select name, memo, owner, date, cid, catid, color from code_name order by lower(name)")
        result = cur.fetchall()
        keys = 'name', 'memo', 'owner', 'date', 'cid', 'catid', 'color'
        for row in result:
            codes.append(dict(zip(keys, row)))
        return codes, categories

    def write_config_ini(self, settings):
        """ Stores settings for fonts, current coder, directory, and window sizes in .qualcoder folder
        Called by qualcoder.App.load_settings, qualcoder.MainWindow.open_project, settings.DialogSettings
        """

        config = configparser.ConfigParser()
        config['DEFAULT'] = settings
        with open(self.configpath, 'w') as configfile:
            config.write(configfile)

    def _load_config_ini(self):
        config = configparser.ConfigParser()
        config.read(self.configpath)
        default = config['DEFAULT']
        result = dict(default)
        # convert to int can be removed when all manual styles are removed
        if 'fontsize' in default:
            result['fontsize'] = default.getint('fontsize')
        if 'treefontsize' in default:
            result['treefontsize'] = default.getint('treefontsize')
        return result

    def check_and_add_additional_settings(self, data):
        """ Newer features include width and height settings for many dialogs and main window.
        timestamp format
        :param data:  dictionary of most or all settings
        :return: dictionary of all settings
        """

        dict_len = len(data)
        keys = ['mainwindow_w', 'mainwindow_h', 'dialogcodetext_w','dialogcodetext_h',
        'dialogcodeimage_w', 'dialogcodeimage_h', 'dialogviewimage_w', 'dialogviewimage_h',
        'dialogreportcodes_w', 'dialogreportcodes_h', 'dialogmanagefiles_w', 'dialogmanagefiles_h',
        'dialogjournals_w', 'dialogjournals_h', 'dialogsql_w', 'dialogsql_h',
        'dialogcases_w', 'dialogcases_h', 'dialogcasefilemanager_w', 'dialogcasefilemanager_h',
        'dialogmanagesttributes_w', 'dialogmanageattributes_h',
        'dialogcodetext_splitter0', 'dialogcodetext_splitter1', 'dialogcodeimage_splitter0',
        'dialogcodeimage_splitter1', 'dialogreportcodes_splitter0', 'dialogreportcodes_splitter1',
        'dialogjournals_splitter0', 'dialogjournals_splitter1', 'dialogsql_splitter_h0',
        'dialogsql_splitter_h1', 'dialogsql_splitter_v0', 'dialogsql_splitter_v1',
        'dialogcases_splitter0', 'dialogcases_splitter1', 'dialogreportcodefrequencies_w',
        'dialogreportcodefrequencies_h', 'mainwindow_w', 'mainwindow_h',
        'dialogcasefilemanager_splitter0', 'dialogcasefilemanager_splitter1', 'timestampformat',
        'speakernameformat', 'video_w', 'video_h', 'dialogcodeav_w', 'dialogcodeav_h',
        'codeav_abs_pos_x', 'codeav_abs_pos_y', 'viewav_abs_pos_x', 'viewav_abs_pos_y',
        'dialogviewav_w', 'dialogviewav_h', 'viewav_video_pos_x', 'viewav_video_pos_y',
        'codeav_video_pos_x', 'codeav_video_pos_y',
        'bookmark_file_id', 'bookmark_pos', 'dialogcodecrossovers_w', 'dialogcodecrossovers_h',
        'dialogcodecrossovers_splitter0', 'dialogcodecrossovers_splitter1'
        ]
        for key in keys:
            if key not in data:
                data[key] = 0
                if key == "timestampformat":
                    data[key] = "[hh.mm.ss]"
                if key == "speakernameformat":
                    data[key] = "[]"
        # write out new ini file, if needed
        if len(data) > dict_len:
            self.write_config_ini(data)
            logger.info('Added window sizings to config.ini')
        return data

    def merge_settings_with_default_stylesheet(self, settings):
        """ Originally had separate stylesheet file. Now stylesheet is coded because
        avoids potential data file import errors with pyinstaller. """

        stylesheet = "* {font-size: 16px;}\n\
        QWidget:focus {border: 2px solid #f89407;}\n\
        QComboBox:hover,QPushButton:hover {border: 2px solid #ffaa00;}\n\
        QGroupBox {border: None;}\n\
        QGroupBox:focus {border: 3px solid #ffaa00;}\n\
        QTextEdit:focus {border: 2px solid #ffaa00;}\n\
        QTableWidget:focus {border: 3px solid #ffaa00;}\n\
        QTreeWidget {font-size: 14px;}"
        stylesheet = stylesheet.replace("* {font-size: 16", "* {font-size:" + str(settings.get('fontsize')))
        stylesheet = stylesheet.replace("QTreeWidget {font-size: 14", "QTreeWidget {font-size: " + str(settings.get('treefontsize')))
        return stylesheet

    def load_settings(self):
        result = self._load_config_ini()
        if not len(result):
            self.write_config_ini(self.default_settings)
            logger.info('Initialized config.ini')
            result = self._load_config_ini()
        result = self.check_and_add_additional_settings(result)
        #TODO TEMPORARY delete in 2021
        if result['speakernameformat'] == 0:
            result['speakernameformat'] = "[]"
        return result

    @property
    def default_settings(self):
        """ bookmark for text files. """
        return {
            'codername': 'default',
            'font': 'Noto Sans',
            'fontsize': 14,
            'treefontsize': 12,
            'directory': os.path.expanduser('~'),
            'showids': False,
            'language': 'en',
            'backup_on_open': True,
            'backup_av_files': True,
            'timestampformat': "[hh.mm.ss]",
            'speakernameformat': "[]",
            'mainwindow_w': 0,
            'mainwindow_h': 0,
            'dialogcodetext_w': 0,
            'dialogcodetext_h': 0,
            'dialogcodetext_splitter0': 1,
            'dialogcodetext_splitter1': 1,
            'dialogcodeimage_w': 0,
            'dialogcodeimage_h': 0,
            'dialogcodeimage_splitter0': 1,
            'dialogcodeimage_splitter1': 1,
            'dialogviewimage_w': 0,
            'dialogviewimage_h': 0,
            'dialogreportcodes_w': 0,
            'dialogreportcodes_h': 0,
            'dialogreportcodefrequencies_w': 0,
            'dialogreportcodefrequencies_h': 0,
            'dialogreportcodes_splitter0': 1,
            'dialogreportcodes_splitter1': 1,
            'dialogmanagefiles_w': 0,
            'dialogmanagefiles_h': 0,
            'dialogjournals_w': 0,
            'dialogjournals_h': 0,
            'dialogjournals_splitter0': 1,
            'dialogjournals_splitter1': 1,
            'dialogsql_w': 0,
            'dialogsql_h': 0,
            'dialogsql_splitter_h0': 1,
            'dialogsql_splitter_h1': 1,
            'dialogsql_splitter_v0': 1,
            'dialogsql_splitter_v1': 1,
            'dialogcases_w': 0,
            'dialogcases_h': 0,
            'dialogcases_splitter0': 1,
            'dialogcases_splitter1': 1,
            'dialogcasefilemanager_w': 0,
            'dialogcasefilemanager_h': 0,
            'dialogcasefilemanager_splitter0': 1,
            'dialogcasefilemanager_splitter1': 1,
            'dialogmanageattributes_w': 0,
            'dialogmanageattributes_h': 0,
            'video_w': 0,
            'video_h': 0,
            'viewav_video_pos_x': 0,
            'viewav_video_pos_y': 0,
            'codeav_video_pos_x': 0,
            'codeav_video_pos_y': 0,
            'dialogcodeav_w': 0,
            'dialogcodeav_h': 0,
            'codeav_abs_pos_x': 0,
            'codeav_abs_pos_y': 0,
            'dialogviewav_w': 0,
            'dialogviewav_h': 0,
            'viewav_abs_pos_x': 0,
            'viewav_abs_pos_y': 0,
            'bookmark_file_id': 0,
            'bookmark_pos': 0,
            'dialogcodecrossovers_w': 0,
            'dialogcodecrossovers_h': 0,
            'dialogcodecrossovers_splitter0': 0,
            'dialogcodecrossovers_splitter1': 0
        }

    def get_file_texts(self, fileids=None):
        """ Get the texts of all text files as a list of dictionaries.
        Called by DialogCodeText.search_for_text
        param:
            fileids - a list of fileids or None
        """

        cur = self.conn.cursor()
        if fileids is not None:
            cur.execute(
                "select name, id, fulltext, memo, owner, date from source where id in (?) and fulltext is not null",
                fileids
            )
        else:
            cur.execute("select name, id, fulltext, memo, owner, date from source where fulltext is not null order by name")
        keys = 'name', 'id', 'fulltext', 'memo', 'owner', 'date'
        result = []
        for row in cur.fetchall():
            result.append(dict(zip(keys, row)))
        return result

    def get_coder_names_in_project(self):
        """ Get all coder names from all tables.
        Useful when opening a project and the settings codername is from another project.
        Possible design flaw is that codernames are not stored in a specific table in the database.
        """

        cur = self.conn.cursor()
        sql = "select owner from code_image union select owner from code_text union select owner from code_av "
        sql += "union select owner from cases union select owner from source union select owner from code_name"
        cur.execute(sql)
        res = cur.fetchall()
        coder_names = []
        for r in res:
            coder_names.append(r[0])
        return coder_names


class MainWindow(QtWidgets.QMainWindow):
    """ Main GUI window.
    Project data is stored in a directory with .qda suffix
    core data is stored in data.qda sqlite file.
    Journal and coding dialogs can be shown non-modally - multiple dialogs open.
    There is a risk of a clash if two coding windows are open with the same file text or
    two journals open with the same journal entry.

    Note: App.settings does not contain projectName, conn or path (to database)
    app.project_name and app.project_path contain these.
    """

    project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
    dialogList = []  # keeps active and track of non-modal windows
    recent_projects = []  # a list of recent projects for the qmenu

    def __init__(self, app, force_quit=False):
        """ Set up user interface from ui_main.py file. """
        self.app = app
        self.force_quit = force_quit
        sys.excepthook = exception_handler
        QtWidgets.QMainWindow.__init__(self)
        self.ui = Ui_MainWindow()
        self.ui.setupUi(self)
        self.get_latest_github_release()
        try:
            w = int(self.app.settings['mainwindow_w'])
            h = int(self.app.settings['mainwindow_h'])
            if h > 40 and w > 50:
                self.resize(w, h)
        except:
            pass
        self.hide_menu_options()
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.init_ui()
        self.show()

    def init_ui(self):
        """ Set up menu triggers """

        # project menu
        self.ui.actionCreate_New_Project.triggered.connect(self.new_project)
        self.ui.actionCreate_New_Project.setShortcut('Ctrl+N')
        self.ui.actionOpen_Project.triggered.connect(self.open_project)
        self.ui.actionOpen_Project.setShortcut('Ctrl+O')
        self.fill_recent_projects_menu_actions()
        self.ui.actionProject_Memo.triggered.connect(self.project_memo)
        self.ui.actionProject_Memo.setShortcut('Ctrl+M')
        self.ui.actionClose_Project.triggered.connect(self.close_project)
        self.ui.actionClose_Project.setShortcut('Alt+X')
        self.ui.actionSettings.triggered.connect(self.change_settings)
        self.ui.actionSettings.setShortcut('Alt+S')
        self.ui.actionProject_summary.triggered.connect(self.project_summary_report)
        self.ui.actionProject_Exchange_Export.triggered.connect(self.REFI_project_export)
        self.ui.actionREFI_Codebook_export.triggered.connect(self.REFI_codebook_export)
        self.ui.actionREFI_Codebook_import.triggered.connect(self.REFI_codebook_import)
        self.ui.actionREFI_QDA_Project_import.triggered.connect(self.REFI_project_import)
        self.ui.actionRQDA_Project_import.triggered.connect(self.rqda_project_import)
        self.ui.actionExit.triggered.connect(self.closeEvent)
        self.ui.actionExit.setShortcut('Ctrl+Q')

        # file cases and journals menu
        self.ui.actionManage_files.triggered.connect(self.manage_files)
        self.ui.actionManage_files.setShortcut('Alt+F')
        self.ui.actionManage_journals.triggered.connect(self.journals)
        self.ui.actionManage_journals.setShortcut('Alt+J')
        self.ui.actionManage_cases.triggered.connect(self.manage_cases)
        self.ui.actionManage_cases.setShortcut('Alt+C')
        self.ui.actionManage_attributes.triggered.connect(self.manage_attributes)
        self.ui.actionManage_attributes.setShortcut('Alt+A')
        self.ui.actionImport_survey.triggered.connect(self.import_survey)
        self.ui.actionImport_survey.setShortcut('Alt+I')

        # codes menu
        self.ui.actionCodes.triggered.connect(self.text_coding)
        self.ui.actionCodes.setShortcut('Alt+T')
        self.ui.actionCode_image.triggered.connect(self.image_coding)
        self.ui.actionCode_image.setShortcut('Alt+I')
        self.ui.actionCode_audio_video.triggered.connect(self.av_coding)
        self.ui.actionCode_audio_video.setShortcut('Alt+V')
        self.ui.actionExport_codebook.triggered.connect(self.codebook)

        # reports menu
        self.ui.actionCoding_reports.triggered.connect(self.report_coding)
        self.ui.actionCoding_reports.setShortcut('Ctrl+R')
        self.ui.actionCoding_comparison.triggered.connect(self.report_coding_comparison)
        self.ui.actionCode_frequencies.triggered.connect(self.report_code_frequencies)
        self.ui.actionView_Graph.triggered.connect(self.view_graph_original)
        self.ui.actionView_Graph.setShortcut('Ctrl+G')
        self.ui.actionCode_relations.triggered.connect(self.report_code_relations)
        #TODO self.ui.actionText_mining.triggered.connect(self.text_mining)
        self.ui.actionSQL_statements.triggered.connect(self.report_sql)

        # help menu
        self.ui.actionContents.triggered.connect(self.help)
        self.ui.actionContents.setShortcut('Ctrl+H')
        self.ui.actionAbout.triggered.connect(self.about)

        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        self.ui.textEdit.setReadOnly(True)
        self.settings_report()

    def resizeEvent(self, new_size):
        """ Update the widget size details in the app.settings variables """

        self.app.settings['mainwindow_w'] = new_size.size().width()
        self.app.settings['mainwindow_h'] = new_size.size().height()

    def fill_recent_projects_menu_actions(self):
        """ Get the recent projects from the .qualcoder txt file.
        Add up to 7 recent projects to the menu. """

        self.recent_projects = self.app.read_previous_project_paths()
        if len(self.recent_projects) == 0:
            return
        # removes the qtdesigner default action. Also clears the section when a proect is closed
        # so that the options for recent projects can be updated
        self.ui.menuOpen_Recent_Project.clear()
        #TODO must be a better way to do this
        for i, r in enumerate(self.recent_projects):
            display_name = r
            if len(r.split("|")) == 2:
                display_name = r.split("|")[1]
            if i == 0:
                action0 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action0)
                action0.triggered.connect(self.project0)
            if i == 1:
                action1 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action1)
                action1.triggered.connect(self.project1)
            if i == 2:
                action2 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action2)
                action2.triggered.connect(self.project2)
            if i == 3:
                action3 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action3)
                action3.triggered.connect(self.project3)
            if i == 4:
                action4 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action4)
                action4.triggered.connect(self.project4)
            if i == 5:
                action5 = QtWidgets.QAction(display_name, self)
                self.ui.menuOpen_Recent_Project.addAction(action5)
                action5.triggered.connect(self.project5)

    def project0(self):
        self.open_project(self.recent_projects[0])

    def project1(self):
        self.open_project(self.recent_projects[1])

    def project2(self):
        self.open_project(self.recent_projects[2])

    def project3(self):
        self.open_project(self.recent_projects[3])

    def project4(self):
        self.open_project(self.recent_projects[4])

    def project5(self):
        self.open_project(self.recent_projects[5])

    def hide_menu_options(self):
        """ No project opened, hide most menu options.
         Enable project import options."""

        # project menu
        self.ui.actionClose_Project.setEnabled(False)
        self.ui.actionProject_Memo.setEnabled(False)
        self.ui.actionProject_Exchange_Export.setEnabled(False)
        self.ui.actionREFI_Codebook_export.setEnabled(False)
        self.ui.actionREFI_Codebook_import.setEnabled(False)
        self.ui.actionREFI_QDA_Project_import.setEnabled(True)
        self.ui.actionRQDA_Project_import.setEnabled(True)
        self.ui.actionExport_codebook.setEnabled(False)
        # files cases journals menu
        self.ui.actionManage_files.setEnabled(False)
        self.ui.actionManage_journals.setEnabled(False)
        self.ui.actionManage_cases.setEnabled(False)
        self.ui.actionManage_attributes.setEnabled(False)
        self.ui.actionImport_survey.setEnabled(False)
        # codes menu
        self.ui.actionCodes.setEnabled(False)
        self.ui.actionCode_image.setEnabled(False)
        self.ui.actionCode_audio_video.setEnabled(False)
        self.ui.actionCategories.setEnabled(False)
        self.ui.actionView_Graph.setEnabled(False)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(False)
        self.ui.actionCoding_comparison.setEnabled(False)
        self.ui.actionCode_frequencies.setEnabled(False)
        self.ui.actionCode_relations.setEnabled(False)
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionSQL_statements.setEnabled(False)

    def show_menu_options(self):
        """ Project opened, show most menu options.
         Disable project import options. """

        # project menu
        self.ui.actionClose_Project.setEnabled(True)
        self.ui.actionProject_Memo.setEnabled(True)
        self.ui.actionProject_Exchange_Export.setEnabled(True)
        self.ui.actionREFI_Codebook_export.setEnabled(True)
        self.ui.actionREFI_Codebook_import.setEnabled(True)
        self.ui.actionREFI_QDA_Project_import.setEnabled(False)
        self.ui.actionRQDA_Project_import.setEnabled(False)
        self.ui.actionExport_codebook.setEnabled(True)
        # files cases journals menu
        self.ui.actionManage_files.setEnabled(True)
        self.ui.actionManage_journals.setEnabled(True)
        self.ui.actionManage_cases.setEnabled(True)
        self.ui.actionManage_attributes.setEnabled(True)
        self.ui.actionImport_survey.setEnabled(True)
        # codes menu
        self.ui.actionCodes.setEnabled(True)
        self.ui.actionCode_image.setEnabled(True)
        self.ui.actionCode_audio_video.setEnabled(True)
        self.ui.actionCategories.setEnabled(True)
        self.ui.actionView_Graph.setEnabled(True)
        # reports menu
        self.ui.actionCoding_reports.setEnabled(True)
        self.ui.actionCoding_comparison.setEnabled(True)
        self.ui.actionCode_frequencies.setEnabled(True)
        self.ui.actionCode_relations.setEnabled(True)
        self.ui.actionSQL_statements.setEnabled(True)

        #TODO FOR FUTURE EXPANSION text mining
        self.ui.actionText_mining.setEnabled(False)
        self.ui.actionText_mining.setVisible(False)

    def settings_report(self):
        """ Display general settings and project summary """

        msg = _("Settings")
        msg += "\n========\n"
        msg += _("Coder") + ": " + self.app.settings['codername'] + "\n"
        msg += _("Font") + ": " + self.app.settings['font'] + " " + str(self.app.settings['fontsize']) + "\n"
        msg += _("Tree font size") + ": " + str(self.app.settings['treefontsize']) + "\n"
        msg += _("Working directory") + ": " +  self.app.settings['directory']
        msg += "\n" + _("Show IDs") + ": " + str(self.app.settings['showids']) + "\n"
        msg += _("Language") + ": " + self.app.settings['language'] + "\n"
        msg += _("Timestamp format") + ": " + self.app.settings['timestampformat'] + "\n"
        msg += _("Speaker name format") + ": " + str(self.app.settings['speakernameformat']) + "\n"
        msg += _("Backup on open") + ": " + str(self.app.settings['backup_on_open']) + "\n"
        msg += _("Backup AV files") + ": " + str(self.app.settings['backup_av_files'])
        if platform.system() == "Windows":
            msg += "\n" + _("Directory (folder) paths / represents \\")
        msg += "\n========"
        self.ui.textEdit.append(msg)

    def report_sql(self):
        """ Run SQL statements on database. """

        ui = DialogSQL(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    """def text_mining(self):
        ''' text analysis of files / cases / codings.
        NOT CURRENTLY IMPLEMENTED, FOR FUTURE EXPANSION.
        '''

        ui = DialogTextMining(self.app, self.ui.textEdit)
        ui.show()"""

    def report_coding_comparison(self):
        """ Compare two or more coders using Cohens Kappa. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogReportCoderComparisons":
                d.show()
                d.activateWindow()
                return
        ui = DialogReportCoderComparisons(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_code_frequencies(self):
        """ Show code frequencies overall and by coder. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogReportCodeFrequencies":
                d.show()
                d.activateWindow()
                return

        ui = DialogReportCodeFrequencies(self.app, self.ui.textEdit, self.dialogList)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_code_relations(self):
        """ Show code relations in text files. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogReportRelations":
                d.show()
                d.activateWindow()
                return
        ui = DialogReportRelations(self.app, self.ui.textEdit, self.dialogList)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def report_coding(self):
        """ Report on coding and categories. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogReportCodes":
                d.show()
                d.activateWindow()
                return

        ui = DialogReportCodes(self.app, self.ui.textEdit, self.dialogList)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def view_graph_original(self):
        """ Show acyclic graph of codes and categories. """

        for d in self.dialogList:
            if type(d).__name__ == "ViewGraphOriginal":
                d.show()
                d.activateWindow()
                return
        ui = ViewGraphOriginal(self.app)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def help(self):
        """ Display manual in browser. """

        webbrowser.open(path + "/GUI/QualCoder_Manual.pdf")
        self.clean_dialog_refs()

    def about(self):
        """ About dialog. """

        ui = DialogInformation(self.app, "About", "")
        ui.exec_()
        self.clean_dialog_refs()

    def manage_attributes(self):
        """ Create, edit, delete, rename attributes. """

        ui = DialogManageAttributes(self.app, self.ui.textEdit)
        ui.exec_()
        self.clean_dialog_refs()

    def import_survey(self):
        """ Import survey flat sheet: csv file or xlsx.
        Create cases and assign attributes to cases.
        Identify qualitative questions and assign these data to the source table for
        coding and review. Modal dialog. """

        ui = DialogImportSurvey(self.app, self.ui.textEdit)
        ui.exec_()
        self.clean_dialog_refs()

    def manage_cases(self):
        """ Create, edit, delete, rename cases, add cases to files or parts of
        files, add memos to cases. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCases":
                d.show()
                d.activateWindow()
                return
        ui = DialogCases(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def manage_files(self):
        """ Create text files or import files from odt, docx, html and
        plain text. Rename, delete and add memos to files.
        """

        for d in self.dialogList:
            if type(d).__name__ == "DialogManageFiles":
                d.show()
                d.activateWindow()
                return
        ui = DialogManageFiles(self.app, self.ui.textEdit)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def journals(self):
        """ Create and edit journals. """

        for d in self.dialogList:
            # Had to add this code to fix error:
            # __main__.clean_dialog_refs wrapped C/C++ object of type DialogJournals has been deleted
            if type(d).__name__ == "DialogJournals":
                try:
                    d.show()
                    d.activateWindow()
                    return
                except Exception as e:
                    logger.debug(str(e))

        ui = DialogJournals(self.app, self.ui.textEdit)
        ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
        self.dialogList.append(ui)
        ui.show()
        self.clean_dialog_refs()

    def text_coding(self):
        """ Create edit and delete codes. Apply and remove codes and annotations to the
        text in imported text files. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCodeText":
                try:
                    d.show()
                    d.activateWindow()
                except RuntimeError as e:
                    logger.debug(str(e))
                    self.dialogList.remove(d)
                return

        files = self.app.get_text_filenames()
        if len(files) > 0:
            ui = DialogCodeText(self.app, self.ui.textEdit, self.dialogList)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.dialogList.append(ui)
            ui.show()
        else:
            msg = _("This project contains no text files.")
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('No text files'))
            mb.setText(msg)
            mb.exec_()
        self.clean_dialog_refs()

    def image_coding(self):
        """ Create edit and delete codes. Apply and remove codes to the image (or regions)
        """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCodeImage":
                d.show()
                d.activateWindow()
                return
        files = self.app.get_image_filenames()
        if len(files) > 0:
            ui = DialogCodeImage(self.app, self.ui.textEdit, self.dialogList)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.dialogList.append(ui)
            ui.show()
        else:
            msg = _("This project contains no image files.")
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('No image files'))
            mb.setText(msg)
            mb.exec_()
        self.clean_dialog_refs()

    def av_coding(self):
        """ Create edit and delete codes. Apply and remove codes to segements of the
        audio or video file. Added try block in case VLC bindings do not work. """

        for d in self.dialogList:
            if type(d).__name__ == "DialogCodeAV":
                try:
                    d.show()
                    d.activateWindow()
                except Exception as e:
                    logger.debug(str(e))
                    try:
                        self.dialogList.remove(d)
                    except:
                        pass
                return

        files = self.app.get_av_filenames()
        if len(files) == 0:
            msg = _("This project contains no audio/video files.")
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('No a/v files'))
            mb.setText(msg)
            mb.exec_()
            self.clean_dialog_refs()
            return

        try:
            ui = DialogCodeAV(self.app, self.ui.textEdit, self.dialogList)
            ui.setAttribute(QtCore.Qt.WA_DeleteOnClose)
            self.dialogList.append(ui)
            ui.show()
        except Exception as e:
            logger.debug(str(e))
            print(e)
            QtWidgets.QMessageBox.warning(None, "A/V Coding", str(e), QtWidgets.QMessageBox.Ok)
        self.clean_dialog_refs()

    def codebook(self):
        """ Export a text file code book of categories and codes.
        """

        Codebook(self.app, self.ui.textEdit)

    def REFI_project_export(self):
        """ Export the project as a qpdx zipped folder.
         Follows the REFI Project Exchange standards.
         CURRENTLY IN TESTING AND NOT COMPLETE NOR VALIDATED.
        VARIABLES ARE NOT SUCCESSFULLY EXPORTED YET.
        CURRENTLY GIFS ARE EXPORTED UNCHANGED (NEED TO BE PNG OR JPG)"""

        Refi_export(self.app, self.ui.textEdit, "project")
        msg = "NOT FULLY TESTED - EXPERIMENTAL\n"
        QtWidgets.QMessageBox.warning(None, "REFI QDA Project export", msg)

    def REFI_codebook_export(self):
        """ Export the codebook as .qdc
        Follows the REFI standard version 1.0. https://www.qdasoftware.org/
        """
        #
        Refi_export(self.app, self.ui.textEdit, "codebook")

    def REFI_codebook_import(self):
        """ Import a codebook .qdc into an opened project.
        Follows the REFI-QDA standard version 1.0. https://www.qdasoftware.org/
         """

        Refi_import(self.app, self.ui.textEdit, "qdc")

    def REFI_project_import(self):
        """ Import a qpdx QDA project into a new project space.
        Follows the REFI standard. """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING REFI-QDA PROJECT"))
        msg = _(
            "Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the QDPX file.")
        mb = QtWidgets.QMessageBox()
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('REFI-QDA import steps'))
        mb.setText(msg)
        mb.exec_()
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            QtWidgets.QMessageBox.warning(None, "Project creation", "Project not successfully created")
            return

        Refi_import(self.app, self.ui.textEdit, "qdpx")
        msg = "EXPERIMENTAL - NOT FULLY TESTED\n"
        msg += "Audio, video, transcripts, transcript codings and synchpoints not tested.\n"
        msg += "Sets and Graphs not imported as QualCoder does not have this functionality.\n"
        msg += "External sources over 2GB not imported or linked to."
        msg += "\n\nPlease, change the coder name in Settings to the current coder name\notherwise coded text and media may appear uncoded."
        QtWidgets.QMessageBox.warning(None, "REFI QDA Project import", _(msg))

    def rqda_project_import(self):
        """ Import an RQDA format project into a new project space. """

        self.close_project()
        self.ui.textEdit.append(_("IMPORTING RQDA PROJECT"))
        msg = _("Step 1: You will be asked for a new QualCoder project name.\nStep 2: You will be asked for the RQDA file.")
        mb = QtWidgets.QMessageBox()
        mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
        mb.setWindowTitle(_('RQDA import steps'))
        mb.setText(msg)
        mb.exec_()
        self.new_project()
        # check project created successfully
        if self.app.project_name == "":
            mb = QtWidgets.QMessageBox()
            mb.setStyleSheet("* {font-size:" + str(self.app.settings['fontsize']) + "pt} ")
            mb.setWindowTitle(_('Project creation'))
            mb.setText(_("Project not successfully created"))
            mb.exec_()
            return
        Rqda_import(self.app, self.ui.textEdit)
        self.project_summary_report()

    def closeEvent(self, event):
        """ Override the QWindow close event.
        Close all dialogs and database connection.
        If selected via menu option exit: event == False
        If selected via window x close: event == QtGui.QCloseEvent
        Close project will also delete a backup if a backup was made and no changes occured.
        """

        if not self.force_quit:
            quit_msg = _("Are you sure you want to quit?")
            reply = QtWidgets.QMessageBox.question(self, 'Message', quit_msg,
            QtWidgets.QMessageBox.Yes, QtWidgets.QMessageBox.No)
            if reply == QtWidgets.QMessageBox.Yes:
                # close project before the dialog list, as close project clean the dialogs
                self.close_project()
                self.dialogList = None

                if self.app.conn is not None:
                    try:
                        self.app.conn.commit()
                        self.app.conn.close()
                    except:
                        pass
                QtWidgets.qApp.quit()
                return
            if event is False:
                return
            else:
                event.ignore()

    def new_project(self):
        """ Create a new project folder with data.qda (sqlite) and folders for documents,
        images, audio and video.
        Note the database does not keep a table specifically for users (coders), instead
        usernames can be freely entered through the settings dialog and are collated from
        coded text, images and a/v.
        v2 had added column in code_text table to link to avid in code_av table.
        """

        self.app = App()
        if self.app.settings['directory'] == "":
            self.app.settings['directory'] = os.path.expanduser('~')
        self.app.project_path = QtWidgets.QFileDialog.getSaveFileName(self,
            _("Enter project name"), self.app.settings['directory'], ".qda")[0]
        if self.app.project_path == "":
            QtWidgets.QMessageBox.warning(None, _("Project"), _("No project created."))
            return
        if self.app.project_path.find(".qda") == -1:
            self.app.project_path = self.app.project_path + ".qda"
        try:
            os.mkdir(self.app.project_path)
            os.mkdir(self.app.project_path + "/images")
            os.mkdir(self.app.project_path + "/audio")
            os.mkdir(self.app.project_path + "/video")
            os.mkdir(self.app.project_path + "/documents")
        except Exception as e:
            logger.critical(_("Project creation error ") + str(e))
            QtWidgets.QMessageBox.warning(None, _("Project"), _("No project created. Exiting. ") + str(e))
            exit(0)
        self.app.project_name = self.app.project_path.rpartition('/')[2]
        self.app.settings['directory'] = self.app.project_path.rpartition('/')[0]
        self.app.create_connection(self.app.project_path)
        cur = self.app.conn.cursor()
        cur.execute("CREATE TABLE project (databaseversion text, date text, memo text,about text);")
        cur.execute("CREATE TABLE source (id integer primary key, name text, fulltext text, mediapath text, memo text, owner text, date text, unique(name));")
        cur.execute("CREATE TABLE code_image (imid integer primary key,id integer,x1 integer, y1 integer, width integer, height integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE code_av (avid integer primary key,id integer,pos0 integer, pos1 integer, cid integer, memo text, date text, owner text);")
        cur.execute("CREATE TABLE annotation (anid integer primary key, fid integer,pos0 integer, pos1 integer, memo text, owner text, date text);")
        cur.execute("CREATE TABLE attribute_type (name text primary key, date text, owner text, memo text, caseOrFile text, valuetype text);")
        cur.execute("CREATE TABLE attribute (attrid integer primary key, name text, attr_type text, value text, id integer, date text, owner text);")
        cur.execute("CREATE TABLE case_text (id integer primary key, caseid integer, fid integer, pos0 integer, pos1 integer, owner text, date text, memo text);")
        cur.execute("CREATE TABLE cases (caseid integer primary key, name text, memo text, owner text,date text, constraint ucm unique(name));")
        cur.execute("CREATE TABLE code_cat (catid integer primary key, name text, owner text, date text, memo text, supercatid integer, unique(name));")
        cur.execute("CREATE TABLE code_text (cid integer, fid integer,seltext text, pos0 integer, pos1 integer, owner text, date text, memo text, avid integer, unique(cid,fid,pos0,pos1, owner));")
        cur.execute("CREATE TABLE code_name (cid integer primary key, name text, memo text, catid integer, owner text,date text, color text, unique(name));")
        cur.execute("CREATE TABLE journal (jid integer primary key, name text, jentry text, date text, owner text);")
        cur.execute("INSERT INTO project VALUES(?,?,?,?)", ('v2',datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S"),'','QualCoder'))
        self.app.conn.commit()
        try:
            # get and display some project details
            self.ui.textEdit.append("\n" + _("New project: ") + self.app.project_path + _(" created."))
            #self.settings['projectName'] = self.path.rpartition('/')[2]
            self.ui.textEdit.append(_("Opening: ") + self.app.project_path)
            self.setWindowTitle("QualCoder " + self.app.project_name)
            cur.execute('select sqlite_version()')
            self.ui.textEdit.append("SQLite version: " + str(cur.fetchone()))
            cur.execute("select databaseversion, date, memo, about from project")
            result = cur.fetchone()
            self.project['databaseversion'] = result[0]
            self.project['date'] = result[1]
            self.project['memo'] = result[2]
            self.project['about'] = result[3]
            self.ui.textEdit.append(_("New Project Created") + "\n========\n"
                + _("DB Version:") + str(self.project['databaseversion']) + "\n"
                + _("Date: ") + str(self.project['date']) + "\n"
                + _("About: ") + str(self.project['about']) + "\n"
                + _("Coder:") + str(self.app.settings['codername']) + "\n"
                + "========")
        except Exception as e:
            msg = _("Problem creating database ")
            logger.warning(msg + self.app.project_path + " Exception:" + str(e))
            self.ui.textEdit.append("\n" + msg + "\n" + self.app.project_path)
            self.ui.textEdit.append(str(e))
            self.close_project()
            return
        # new project, so tell open project NOT to backup, as there will be nothing in there to backup
        self.open_project(self.app.project_path, "yes")

    def change_settings(self):
        """ Change default settings - the coder name, font, font size. Non-modal.
        Backup options """

        current_coder = self.app.settings['codername']
        ui = DialogSettings(self.app)
        ui.exec_()
        self.settings_report()
        font = 'font: ' + str(self.app.settings['fontsize']) + 'pt '
        font += '"' + self.app.settings['font'] + '";'
        self.setStyleSheet(font)
        if current_coder != self.app.settings['codername']:
            # Close all opened dialogs as coder name needs to change everywhere
            self.clean_dialog_refs()
            for d in self.dialogList:
                d.destroy()
                self.dialogList = []

    def project_memo(self):
        """ Give the entire project a memo. Modal dialog. """

        cur = self.app.conn.cursor()
        cur.execute("select memo from project")
        memo = cur.fetchone()[0]
        ui = DialogMemo(self.app, _("Memo for project ") + self.app.project_name,
            memo)
        self.dialogList.append(ui)
        ui.exec_()
        if memo != ui.memo:
            cur.execute('update project set memo=?', (ui.memo,))
            self.app.conn.commit()
            self.ui.textEdit.append(_("Project memo entered."))
            self.app.delete_backup = False

    def open_project(self, path="", newproject="no"):
        """ Open an existing project.
        if set, also save a backup datetime stamped copy at the same time.
        Do not backup on a newly created project, as it wont contain data.
        A backup is created if settings backuop is True.
        The backup is deleted, if no changes occured.
        Backups are created using the date and 24 hour suffix: _BKUP_yyyymmdd_hh
        Backups are not replaced within the same hour.
        param:
            path: if path is "" then get the path from a dialog, otherwise use the supplied path
            newproject: yes or no  if yes then do not make an initial backup
        """

        default_directory = self.app.settings['directory']
        if path == "" or path is False:
            if default_directory == "":
                default_directory = os.path.expanduser('~')
            path = QtWidgets.QFileDialog.getExistingDirectory(self,
                _('Open project directory'), default_directory)
        if path == "" or path is False:
            return
        self.close_project()
        msg = ""
        # New path variable from recent_projects.txt contains time | path
        # Older variable only listed the project path
        splt = path.split("|")
        proj_path = ""
        if len(splt) == 1:
            proj_path = splt[0]
        if len(splt) == 2:
            proj_path = splt[1]
        if len(path) > 3 and proj_path[-4:] == ".qda":
            try:
                self.app.create_connection(proj_path)
            except Exception as e:
                self.app.conn = None
                msg += " " + str(e)
                logger.debug(msg)
        if self.app.conn is None:
            msg += "\n" + proj_path
            QtWidgets.QMessageBox.warning(None, _("Cannot open file"),
                msg)
            self.app.project_path = ""
            self.app.project_name = ""
            return

        #TODO Potential design flaw to have the current coders name in the config.ini file
        #TODO as is would change when opening different projects
        # Check that the coder name from setting ini file is in the project
        # If not then replace with a name in the project
        names = self.app.get_coder_names_in_project()
        if self.app.settings['codername'] not in names and len(names) > 0:
            self.app.settings['codername'] = names[0]
            self.app.write_config_ini(self.app.settings)
            self.ui.textEdit.append(_("Default coder name changed to: ") + names[0])
        # get and display some project details
        self.app.append_recent_project(self.app.project_path)
        self.fill_recent_projects_menu_actions()
        self.setWindowTitle("QualCoder " + self.app.project_name)

        # check avid column in code_text table
        # database version < 2
        cur = self.app.conn.cursor()
        try:
            cur.execute("select avid from code_text")
        except:
            cur.execute("ALTER TABLE code_text ADD avid integer;")
            self.app.conn.commit()

        # Save a date and 24hour stamped backup
        if self.app.settings['backup_on_open'] == 'True' and newproject == "no":
            self.save_backup()
        msg = "\n========\n" + _("Project Opened: ") + self.app.project_name
        self.ui.textEdit.append(msg)
        self.project_summary_report()
        self.show_menu_options()

    def save_backup(self):
        """ Save a date and hours stamped backup.
        Do not backup if the name already exists.
        A back up can be generated in the subsequent hour."""

        nowdate = datetime.datetime.now().astimezone().strftime("%Y%m%d_%H")  # -%M-%S")
        backup = self.app.project_path[0:-4] + "_BKUP_" + nowdate + ".qda"
        # Do not try and create another backup with same date and hour
        result = os.path.exists(backup)
        if result:
            return
        if self.app.settings['backup_av_files'] == 'True':
            try:
                shutil.copytree(self.app.project_path, backup)
            except FileExistsError as e:
                msg = _("There is already a backup with this name")
                print(str(e) + "\n" + msg)
                logger.warning(_(msg) + "\n" + str(e))
        else:
            shutil.copytree(self.app.project_path, backup,
            ignore=shutil.ignore_patterns('*.mp3', '*.wav', '*.mp4', '*.mov', '*.ogg', '*.wmv', '*.MP3',
                '*.WAV', '*.MP4', '*.MOV', '*.OGG', '*.WMV'))
            self.ui.textEdit.append(_("WARNING: audio and video files NOT backed up. See settings."))
        self.ui.textEdit.append(_("Project backup created: ") + backup)
        # delete backup path - delete the backup if no changes occurred in the project during the session
        self.app.delete_backup_path_name = backup

    def project_summary_report(self):
        """ Add a summary of the project to the tet edit.
         Display project memo, and code, attribute, journal, files frequencies."""

        os_type = platform.system()
        if self.app.conn is None:
            return
        cur = self.app.conn.cursor()
        cur.execute("select databaseversion, date, memo, about from project")
        result = cur.fetchall()[-1]
        self.project['databaseversion'] = result[0]
        self.project['date'] = result[1]
        self.project['memo'] = result[2]
        #self.project['about'] = result[3]
        msg = "\n" + _("PROJECT SUMMARY")
        msg += "\n========\n"
        msg += _("Date time now: ") + datetime.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M") + "\n"
        msg += self.app.project_name + "\n"
        msg += _("Project path: ") + self.app.project_path + "\n"
        #msg += _("Database version: ") + self.project['databaseversion'] + ". "
        msg+= _("Project date: ") + str(self.project['date']) + "\n"
        sql = "select memo from project"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Project memo: ") + str(res[0]) + "\n"
        sql = "select count(id) from source"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Files: ") + str(res[0]) + "\n"
        sql = "select count(caseid) from cases"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Cases: ") + str(res[0]) + "\n"
        sql = "select count(catid) from code_cat"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Code categories: ") + str(res[0]) + "\n"
        sql = "select count(cid) from code_name"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Codes: ") + str(res[0]) + "\n"
        sql = "select count(name) from attribute_type"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Attributes: ") + str(res[0]) + "\n"
        sql = "select count(jid) from journal"
        cur.execute(sql)
        res = cur.fetchone()
        msg += _("Journals: ") + str(res[0])

        msg += "\nText Bookmark: " + str(self.app.settings['bookmark_file_id'])
        msg += ", position: " + str(self.app.settings['bookmark_pos'])

        if platform.system() == "Windows":
            msg += "\n" + _("Directory (folder) paths / represents \\")
        msg += "\n========\n"
        self.ui.textEdit.append(msg)

    def close_project(self):
        """ Close an open project. """

        self.ui.textEdit.append("Closing project: " + self.app.project_name + "\n========\n")
        try:
            self.app.conn.commit()
            self.app.conn.close()
        except:
            pass
        self.delete_backup_folders()
        self.app.append_recent_project(self.app.project_path)
        self.fill_recent_projects_menu_actions()
        self.app.conn = None
        self.app.project_path = ""
        self.app.project_name = ""
        self.app.delete_backup_path_name = ""
        self.app.delete_backup = True
        self.project = {"databaseversion": "", "date": "", "memo": "", "about": ""}
        self.hide_menu_options()
        self.clean_dialog_refs()
        for d in self.dialogList:
            d.destroy()
            self.dialogList = []
        self.setWindowTitle("QualCoder")
        self.app.write_config_ini(self.app.settings)

    def delete_backup_folders(self):
        """ Delete the most current backup created on opening a project,
        providing the project was not changed in any way.
        Delete oldest backups if more than 5 are created.
        Backup name format:
        directories/projectname_BKUP_yyyymmdd_hh.qda
        Keep up to FIVE backups only. """

        if self.app.project_path == "":
            return
        if self.app.delete_backup_path_name != "" and self.app.delete_backup:
            try:
                shutil.rmtree(self.app.delete_backup_path_name)
            except Exception as e:
                print(str(e))

        # Get a list of backup folders for current project
        parts = self.app.project_path.split('/')
        projectname_and_suffix = parts[-1]
        directory = self.app.project_path[0:-len(projectname_and_suffix)]
        projectname = projectname_and_suffix[:-4]
        projectname_and_bkup = projectname + "_BKUP_"
        lenname = len(projectname_and_bkup)
        files_folders = os.listdir(directory)
        backups = []
        for f in files_folders:
            if f[0:lenname] == projectname_and_bkup and f[-4:] == ".qda":
                backups.append(f)
        # Sort newest to oldest, and remove any that are more than fifth positon in the list
        backups.sort(reverse=True)
        to_remove = []
        if len(backups) > 5:
            to_remove = backups[5:]
        if to_remove == []:
            return
        for f in to_remove:
            try:
                print("Removing " + directory + f)
                shutil.rmtree(directory + f)
                self.ui.textEdit.append(_("Deleting: " + f))
            except Exception as e:
                print(str(e))

    def clean_dialog_refs(self):
        """ Test the list of dialog refs to see if they have been cleared
        and create a new list of current dialogs.
        Also need to keep these dialog references to keep non-modal dialogs open.
        Non-modal example - having a journal open and a coding dialog. """

        tempList = []
        for d in self.dialogList:
            try:
                #logger.debug(str(d) + ", isVisible:" + str(d.isVisible()) + " Title:" + d.windowTitle())
                if d.isVisible():
                    tempList.append(d)
            # RuntimeError: wrapped C/C++ object of type DialogSQL has been deleted
            except RuntimeError as e:
                #logger.error(str(e))
                pass
        self.dialogList = tempList
        self.update_dialog_lists_in_modeless_dialogs()

    def update_dialog_lists_in_modeless_dialogs(self):
        """ This is to assist: Update code and category tree in DialogCodeImage,
        DialogCodeAV, DialogCodeText, DialogReportCodes """

        for d in self.dialogList:
            if isinstance(d, DialogCodeText):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogCodeAV):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogCodeImage):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogReportCodes):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogCases):
                d.dialog_list = self.dialogList
            if isinstance(d, DialogManageFiles):
                d.dialog_list = self.dialogList

    def get_latest_github_release(self):
        """ Get latest github release.
        https://stackoverflow.com/questions/24987542/is-there-a-link-to-github-for-downloading-a-file-in-the-latest-release-of-a-repo
        Dated May 2018

        Some issues on some platforms, so all in try except clause
        """

        self.ui.textEdit.append(_("This version: ") + qualcoder_version)
        try:
            _json = json.loads(urllib.request.urlopen(urllib.request.Request(
                'https://api.github.com/repos/ccbogel/QualCoder/releases/latest',
                headers={'Accept': 'application/vnd.github.v3+json'},
            )).read())
            if _json['name'] not in qualcoder_version:
                html = '<span style="color:red">' + _("Newer release available: ") + _json['name'] + '</span>'
                self.ui.textEdit.append(html)
                html = '<span style="color:red">' + _json['html_url'] + '</span><br />'
                self.ui.textEdit.append(html)
            else:
                self.ui.textEdit.append(_("Latest Release: ") + _json['name'])
                self.ui.textEdit.append(_json['html_url'] + "\n")
                #asset = _json['assets'][0]
                #urllib.request.urlretrieve(asset['browser_download_url'], asset['name'])
        except Exception as e:
            print(e)
            logger.debug(str(e))
            self.ui.textEdit.append(_("Could not detect latest release from Github\n") + str(e))


def gui():
    qual_app = App()
    settings = qual_app.load_settings()
    project_path = qual_app.get_most_recent_projectpath()
    app = QtWidgets.QApplication(sys.argv)
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Regular.ttf")
    QtGui.QFontDatabase.addApplicationFont("GUI/NotoSans-hinted/NotoSans-Bold.ttf")
    stylesheet = qual_app.merge_settings_with_default_stylesheet(settings)
    app.setStyleSheet(stylesheet)
    # Try and load language settings from file stored in home/.qualcoder/
    # translator applies to ui designed GUI widgets only
    lang = settings.get('language', 'en')
    getlang = gettext.translation('en', localedir=path +'/locale', languages=['en'])
    #if lang != "en":
    if lang in ["de", "el", "es", "fr", "jp"]:
        translator = QtCore.QTranslator()
        translator.load(path + "/locale/" + lang + "/app_" + lang + ".qm")
        getlang = gettext.translation(lang, localedir=path + '/locale', languages=[lang])
        app.installTranslator(translator)
    getlang.install()
    ex = MainWindow(qual_app)
    if project_path:
        split_ = project_path.split("|")
        proj_path = ""
        # Only the path - older and rarer format - legacy
        if len(split_) == 1:
            proj_path = split_[0]
        # Newer datetime | path
        if len(split_) == 2:
            proj_path = split_[1]
        ex.open_project(path=proj_path)
    sys.exit(app.exec_())


if __name__ == "__main__":
    gui()
