import os
import ast
import shutil
import qt
import vtk
import ctk
import slicer

from ProstateAblationUtils.constants import ProstateAblationConstants
from ProstateAblationUtils.steps.base import ProstateAblationPlugin

from SlicerDevelopmentToolboxUtils.helpers import SampleDataDownloader
from SlicerDevelopmentToolboxUtils.decorators import *


class ProstateAblationTrainingPlugin(ProstateAblationPlugin):

  NAME = "Training"

  def __init__(self, ProstateAblationSession):
    super(ProstateAblationTrainingPlugin, self).__init__(ProstateAblationSession)
    self.sampleDownloader = SampleDataDownloader(True)

  def setup(self):
    super(ProstateAblationTrainingPlugin, self).setup()
    self.collapsibleTrainingArea = ctk.ctkCollapsibleButton()
    self.collapsibleTrainingArea.collapsed = True
    self.collapsibleTrainingArea.text = "Training Incoming Data Simulation"

    self.simulateIntraopPhaseButton = self.createButton("Simulate intraop reception", enabled=True)

    self.trainingsAreaLayout = qt.QGridLayout(self.collapsibleTrainingArea)
    self.trainingsAreaLayout.addWidget(self.createHLayout([self.simulateIntraopPhaseButton]))
    self.layout().addWidget(self.collapsibleTrainingArea)

  def setupConnections(self):
    self.simulateIntraopPhaseButton.clicked.connect(self.startIntraopPhaseSimulation)

  def setupSessionObservers(self):
    super(ProstateAblationTrainingPlugin, self).setupSessionObservers()
    self.session.addEventObserver(self.session.IncomingDataSkippedEvent, self.onIncomingDataSkipped)

  def removeSessionEventObservers(self):
    super(ProstateAblationTrainingPlugin, self).removeSessionEventObservers()
    self.session.removeEventObserver(self.session.IncomingDataSkippedEvent, self.onIncomingDataSkipped)

  def startIntraopPhaseSimulation(self):
    self.simulateIntraopPhaseButton.enabled = True
    intraopZipFile = self.initiateSampleDataDownload(ProstateAblationConstants.INTRAOP_SAMPLE_DATA_URL)
    if not self.sampleDownloader.wasCanceled() and intraopZipFile:
      print(intraopZipFile)
      self.unzipFileAndCopyToDirectory(intraopZipFile, self.session.intraopDICOMDirectory)
      

  def initiateSampleDataDownload(self, url):
    filename = os.path.basename(url)
    self.sampleDownloader.resetAndInitialize()
    self.sampleDownloader.addEventObserver(self.sampleDownloader.StatusChangedEvent, self.onDownloadProgressUpdated)
    # self.customStatusProgressBar.show()
    downloadedFile = self.sampleDownloader.downloadFileIntoCache(url, filename)
    # self.customStatusProgressBar.hide()
    return None if self.sampleDownloader.wasCanceled() else downloadedFile

  @onReturnProcessEvents
  @vtk.calldata_type(vtk.VTK_STRING)
  def onDownloadProgressUpdated(self, caller, event, callData):
    message, percent = ast.literal_eval(callData)
    logging.info("%s, %s" %(message, percent))
    # self.customStatusProgressBar.updateStatus(message, percent)

  def unzipFileAndCopyToDirectory(self, filepath, copyToDirectory):
    import zipfile
    try:
      zip_ref = zipfile.ZipFile(filepath, 'r')
      destination = filepath.replace(os.path.basename(filepath), "")
      logging.debug("extracting to %s " % destination)
      zip_ref.extractall(destination)
      zip_ref.close()
      self.copyDirectory(filepath.replace(".zip", ""), copyToDirectory)
    except zipfile.BadZipfile as exc:
      slicer.util.errorDisplay("An error appeared while extracting %s. If the file is corrupt, please delete it and try "
                               "again." % filepath, detailedText=str(exc.message))
      self.clearData()

  def copyDirectory(self, source, destination, recursive=True):
    print(source)
    assert os.path.isdir(source)
    for listObject in os.listdir(source):
      current = os.path.join(source, listObject)
      if os.path.isdir(current) and recursive:
        self.copyDirectory(current, destination, recursive)
      else:
        shutil.copy(current, destination)

  def onIncomingDataSkipped(self, caller, event):
    self.simulateIntraopPhaseButton.enabled = True

  def onNewCaseStarted(self, caller, event):
    self.simulateIntraopPhaseButton.enabled = True
    pass

  @vtk.calldata_type(vtk.VTK_STRING)
  def onCaseClosed(self, caller, event, callData):
    self.simulateIntraopPhaseButton.enabled = False
    
