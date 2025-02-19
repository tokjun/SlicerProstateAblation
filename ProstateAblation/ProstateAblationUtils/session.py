import os, logging
import vtk, ctk, ast, qt
import numpy
import slicer
from ProstateAblationUtils.sessionData import SessionData
from ProstateAblationUtils.constants import ProstateAblationConstants as constants
from ProstateAblationUtils.steps.plugins.targetsDefinition import TargetsDefinitionPlugin
from ProstateAblationUtils.steps.plugins.targetsDefinitionTable import ZFrameGuidanceComputation
from ProstateAblationUtils.helpers import SeriesTypeManager

from SlicerDevelopmentToolboxUtils.exceptions import DICOMValueError, UnknownSeriesError
from SlicerDevelopmentToolboxUtils.constants import DICOMTAGS, FileExtension, STYLE
from SlicerDevelopmentToolboxUtils.events import SlicerDevelopmentToolboxEvents
from SlicerDevelopmentToolboxUtils.helpers import SmartDICOMReceiver
from SlicerDevelopmentToolboxUtils.mixins import ModuleWidgetMixin, ModuleLogicMixin
from SlicerDevelopmentToolboxUtils.widgets import CustomStatusProgressbar
from SlicerDevelopmentToolboxUtils.decorators import singleton
from SlicerDevelopmentToolboxUtils.decorators import onExceptionReturnFalse, onReturnProcessEvents
from SlicerDevelopmentToolboxUtils.module.session import StepBasedSession

@singleton
class ProstateAblationSession(StepBasedSession):

  IncomingDataSkippedEvent = SlicerDevelopmentToolboxEvents.SkippedEvent
  IncomingIntraopDataReceiveFinishedEvent = SlicerDevelopmentToolboxEvents.FinishedEvent + 111
  NewImageSeriesReceivedEvent = SlicerDevelopmentToolboxEvents.NewImageDataReceivedEvent

  DICOMReceiverStatusChanged = SlicerDevelopmentToolboxEvents.StatusChangedEvent
  DICOMReceiverStoppedEvent = SlicerDevelopmentToolboxEvents.StoppedEvent

  ZFrameRegistrationSuccessfulEvent = vtk.vtkCommand.UserEvent + 140
  LoadingMetadataSuccessfulEvent = vtk.vtkCommand.UserEvent + 143
  SegmentationCancelledEvent = vtk.vtkCommand.UserEvent + 144

  CurrentSeriesChangedEvent = vtk.vtkCommand.UserEvent + 151

  InitiateZFrameCalibrationEvent = vtk.vtkCommand.UserEvent + 160
  InitiateTargetingEvent = vtk.vtkCommand.UserEvent + 161
  NeedleTipLocateEvent = vtk.vtkCommand.UserEvent + 162

  NeedleGuidanceEvent = vtk.vtkCommand.UserEvent + 164

  AffectedAreaDisplayChangedEvent = vtk.vtkCommand.UserEvent + 165

  SeriesTypeManuallyAssignedEvent = SeriesTypeManager.SeriesTypeManuallyAssignedEvent

  MODULE_NAME = constants.MODULE_NAME
  
  NEEDLE_NAME = 'NeedlePath'
  
  AFFECTEDAREA_NAME = "AffectedArea"

  ISSEEDTYPE = "IceSeed"
  ISRODTYPE = "IceRod"
  
  @property
  def intraopDICOMDirectory(self):
    return os.path.join(self.directory, "DICOM", "Intraop") if self.directory else None

  @property
  def outputDirectory(self):
    # was outputDir
    return os.path.join(self.directory, "ProstateAblationOutputs")

  @property
  def approvedCoverTemplate(self):
    try:
      return self.data.zFrameRegistrationResult.volume
    except AttributeError:
      return None

  @approvedCoverTemplate.setter
  def approvedCoverTemplate(self, volume):
    self.data.zFrameRegistrationResult.volume = volume
    self.zFrameRegistrationSuccessful = volume is not None

  @property
  def zFrameRegistrationSuccessful(self):
    self._zFrameRegistrationSuccessful = getattr(self, "_zFrameRegistrationSuccessful", None)
    return self.data.zFrameRegistrationResult is not None and self._zFrameRegistrationSuccessful

  @zFrameRegistrationSuccessful.setter
  def zFrameRegistrationSuccessful(self, value):
    self._zFrameRegistrationSuccessful = value
    if self._zFrameRegistrationSuccessful:
      self.save()
      self.invokeEvent(self.ZFrameRegistrationSuccessfulEvent)

  @property
  def currentSeries(self):
    self._currentSeries = getattr(self, "_currentSeries", None)
    return self._currentSeries

  @currentSeries.setter
  def currentSeries(self, series):
    if series == self.currentSeries:
      return
    print("set current Series on session")
    if series and series not in self.seriesList :
      raise UnknownSeriesError("Series %s is unknown" % series)
    self._currentSeries = series
    self.invokeEvent(self.CurrentSeriesChangedEvent, series)

  @property
  def currentSeriesVolume(self):
    if not self.currentSeries:
      return None
    else:
      return self.getOrCreateVolumeForSeries(self.currentSeries)

  def __init__(self):
    StepBasedSession.__init__(self)
    self.seriesTypeManager = SeriesTypeManager()
    self.seriesTypeManager.addEventObserver(self.seriesTypeManager.SeriesTypeManuallyAssignedEvent,
                                            lambda caller, event: self.invokeEvent(self.SeriesTypeManuallyAssignedEvent))
    self.targetingPlugin = TargetsDefinitionPlugin(self)
    self.needlePathCaculator = ZFrameGuidanceComputation(self)
    self.segmentationEditor = slicer.qMRMLSegmentEditorWidget()
    self.resetAndInitializeMembers()
    self.resetAndInitializedTargetsAndSegments()
  
  def resetAndInitializeMembers(self):
    self.seriesTypeManager.clear()
    self.initializeColorNodes()
    self.directory = None
    self.data = SessionData()
    self.trainingMode = False
    self.resetIntraopDICOMReceiver()
    self.loadableList = {}
    self.seriesList = []
    self.alreadyLoadedSeries = {}
    self._currentSeries = None
    self.retryMode = False
    self.lastSelectedModelIndex = None
    self.previousStep = None

  def resetAndInitializedTargetsAndSegments(self):
    self.displayForTargets = dict()
    self.needleTypeForTargets = dict()
    self.targetingPlugin.cleanup()
    self.needleModelNode = None
    self.affectedAreaModelNode = None
    self.segmentationEditorNoneButton = None
    self.segmentationEditorShow3DButton = None
    self.segmentationEditorMaskOverWriteCombox = None
    self.segmentEditorNode = None
    self.setupNeedleAndSegModelNode()

  def initializeColorNodes(self):
    self.segmentedColorName = self.getSetting("Segmentation_Color_Name")
    
  def __del__(self):
    super(ProstateAblationSession, self).__del__()
    self.clearData()

  def clearData(self):
    slicer.mrmlScene.Clear(0)
    self.resetAndInitializeMembers()
    self.resetAndInitializedTargetsAndSegments()
    self.resetSteps()
  
  def resetSteps(self):
    for step in self.steps:
      step.cleanup()
      
  def onMrmlSceneCleared(self, caller, event):
    self.initializeColorNodes()

  @onExceptionReturnFalse
  def isCurrentSeriesCoverProstate(self):
    return self.seriesTypeManager.isCoverProstate(self.currentSeries)

  def isCaseDirectoryValid(self):
    return os.path.exists(self.intraopDICOMDirectory)

  def isRunning(self):
    return not self.directory in [None, '']
  
  
  def setupFiducialWidgetAndTableWidget(self):
    self.targetingPlugin.fiducialsWidget.addEventObserver(slicer.vtkMRMLMarkupsNode().PointAddedEvent,
                                     self.updateAffectiveZoneAndDistance)
    self.targetingPlugin.fiducialsWidget.addEventObserver(slicer.vtkMRMLMarkupsNode().PointRemovedEvent,
                                                          self.updateAffectiveZoneAndDistance)
    self.targetingPlugin.targetTablePlugin.addEventObserver(self.targetingPlugin.targetTablePlugin.TargetPosUpdatedEvent, self.updateAffectiveZoneAndDistance)


  def processDirectory(self):
    self.newCaseCreated = getattr(self, "newCaseCreated", False)
    if self.newCaseCreated:
      return
    if not self.directory or not self.isCaseDirectoryValid():
      slicer.util.warningDisplay("The selected case directory seems not to be valid", windowTitle="ProstateAblation")
      self.close(save=False)
    else:
      self.loadCaseData()
      self.invokeEvent(self.CaseOpenedEvent)

  def createNewCase(self, destination):
    self.newCaseCreated = True
    self.clearData()
    self.directory = destination
    self.createDirectory(self.intraopDICOMDirectory)
    self.createDirectory(self.outputDirectory)
    self.startIntraopDICOMReceiver()
    self.invokeEvent(self.IncomingDataSkippedEvent)
    self.newCaseCreated = False
    self.invokeEvent(self.NewCaseStartedEvent)

  def close(self, save=False):
    if not self.isRunning():
      return
    message = None
    if save:
      self.data.savedNeedleTypeForTargets = self.needleTypeForTargets.copy()
      success, failedFileNames = self.data.close(self.outputDirectory)
      message = "Case data has been saved successfully." if success else \
        "The following data failed to saved:\n %s" % failedFileNames
    self.invokeEvent(self.CloseCaseEvent, str(message))
    self.clearData()

  def save(self):
    self.data.savedNeedleTypeForTargets = self.needleTypeForTargets.copy()
    success, failedFileNames = self.data.save(self.outputDirectory)
    return success and not len(failedFileNames), "The following data failed to saved:\n %s" % failedFileNames

  def complete(self):
    self.data.completed = True
    self.close(save=True)

  def load(self):
    filename = os.path.join(self.outputDirectory, constants.JSON_FILENAME)
    completed = self.data.wasSessionCompleted(filename)
    if slicer.util.confirmYesNoDisplay("A %s session has been found for the selected case. Do you want to %s?" \
                                        % ("completed" if completed else "started",
                                           "open it" if completed else "continue this session")):
      slicer.app.layoutManager().blockSignals(True)
      self._loading = True
      self.data.load(filename)
      self.postProcessLoadedSessionData()
      self._loading = False
      slicer.app.layoutManager().blockSignals(False)
      self.invokeEvent(self.LoadingMetadataSuccessfulEvent)
    else:
      self.clearData()

  def postProcessLoadedSessionData(self):
    for step in self.steps:
      step.resetAndInitialize()
    if self.data.zFrameRegistrationResult:
      self.setupLoadedTransform()
    self.data.resumed = not self.data.completed
    if self.data.intraOpTargets:
      for fiducialIndex in range(self.data.intraOpTargets.GetNumberOfFiducials()):
        self.displayForTargets[self.data.intraOpTargets.GetNthMarkupID(fiducialIndex)] = qt.Qt.Unchecked
      self.needleTypeForTargets = self.data.savedNeedleTypeForTargets.copy()
      self.targetingPlugin.targetTablePlugin.currentTargets = self.data.intraOpTargets
      self.targetingPlugin.targetTablePlugin.visible = True
      self.targetingPlugin.calculateTargetsDistance()
      self.targetingPlugin.targetDistanceWidget.visible = True
      self.setupLoadedTargets()
    self.startIntraopDICOMReceiver()
    
  def setupSegmentationWidget(self):
    for child in self.segmentationEditor.children():
      if child.className() == 'QGroupBox':
        if child.title == 'Effects':
          self.segmentationEditorNoneButton = child.children()[1]
      if child.className() == 'ctkMenuButton':
        if child.text == ' Show 3D':
          self.segmentationEditorShow3DButton = child
      if child.className() == 'ctkCollapsibleGroupBox':
        if child.title == 'Masking':
          for grandchild in child.children():
            if grandchild.className() == 'QComboBox':
              if grandchild.findText('All segments') > -1 and \
                 grandchild.findText('Visible segments') > -1 and \
                 grandchild.findText('None') > -1:
                self.segmentationEditorMaskOverWriteCombox = grandchild
  
  def clearOldNodesByName(self, name):
    collection = slicer.mrmlScene.GetNodesByName(name)
    for index in range(collection.GetNumberOfItems()):
      slicer.mrmlScene.RemoveNode(collection.GetItemAsObject(index))   
                 
  def setupNeedleAndSegModelNode(self):
    self.clearOldNodesByName(self.NEEDLE_NAME)
    self.setupFiducialWidgetAndTableWidget()
    self.setupSegmentationWidget()
    if self.needleModelNode is None:
      self.needleModelNode = ModuleLogicMixin.createModelNode(self.NEEDLE_NAME)
    if (self.needleModelNode.GetScene() is None) or (not self.needleModelNode.GetScene() == slicer.mrmlScene):
      slicer.mrmlScene.AddNode(self.needleModelNode)
    if self.needleModelNode.GetDisplayNode() is None:
      ModuleLogicMixin.createAndObserveDisplayNode(self.needleModelNode, displayNodeClass=slicer.vtkMRMLModelDisplayNode)
      self.needleModelNode.GetDisplayNode().SetColor(1.0, 0.0, 0.0)
      
    if self.affectedAreaModelNode is None:
      self.affectedAreaModelNode = ModuleLogicMixin.createModelNode(self.AFFECTEDAREA_NAME)
    if (self.affectedAreaModelNode.GetScene() is None) or (not self.affectedAreaModelNode.GetScene() == slicer.mrmlScene):
      slicer.mrmlScene.AddNode(self.affectedAreaModelNode)
    if self.affectedAreaModelNode.GetDisplayNode() is None:
      ModuleLogicMixin.createAndObserveDisplayNode(self.affectedAreaModelNode, displayNodeClass=slicer.vtkMRMLModelDisplayNode)
      self.affectedAreaModelNode.GetDisplayNode().SetOpacity(0.5)
      self.affectedAreaModelNode.GetDisplayNode().SetColor(0.0,1.0,0.0)
      
    if self.data.segmentModelNode is None:
      # Create segmentation
      self.data.segmentModelNode = slicer.vtkMRMLSegmentationNode()
      slicer.mrmlScene.AddNode(self.data.segmentModelNode)
      self.data.segmentModelNode.CreateDefaultDisplayNodes()  # only needed for display
      self.data.segmentModelNode.CreateDefaultStorageNode()
      self.data.segmentModelNode.SetName("IntraOpSegmentation")
    if (self.data.segmentModelNode.GetScene() is None) or (not self.data.segmentModelNode.GetScene() == slicer.mrmlScene):
      slicer.mrmlScene.AddNode(self.data.segmentModelNode) 
    if self.data.segmentModelNode.GetDisplayNode() is None:
      ModuleLogicMixin.createAndObserveDisplayNode(self.data.segmentModelNode,
                                                   displayNodeClass=slicer.vtkMRMLSegmentationDisplayNode)
    if self.segmentEditorNode is None:
      self.segmentEditorNode = slicer.vtkMRMLSegmentEditorNode()
      slicer.mrmlScene.AddNode(self.segmentEditorNode)
    if (self.segmentEditorNode.GetScene() is None) or (not self.segmentEditorNode.GetScene() == slicer.mrmlScene):
      slicer.mrmlScene.AddNode(self.segmentEditorNode)   
    self.segmentationEditor.setMRMLScene(slicer.mrmlScene)
    self.segmentationEditor.setMRMLSegmentEditorNode(self.segmentEditorNode)

    if self.segmentationEditorMaskOverWriteCombox: # TODO: This should exist after setupSegmentationWidget() is called. 
      self.segmentationEditorMaskOverWriteCombox.setCurrentIndex(self.segmentationEditorMaskOverWriteCombox.findText('None'))

  def updateAffectiveZoneAndDistance(self, caller = None, event = None):
    self.updateAffectiveZone()
    self.targetingPlugin.calculateTargetsDistance()

  def onShowAffectiveZoneToggled(self, checked):
    targetingNode = self.targetingPlugin.targetTablePlugin.currentTargets
    if targetingNode is not None:
      for targetIndex in range(targetingNode.GetNumberOfFiducials()):
        checkboxStatus = qt.Qt.Checked if checked else qt.Qt.Unchecked
        self.displayForTargets[targetingNode.GetNthMarkupID(targetIndex)] = checkboxStatus
        if self.targetingPlugin.targetTablePlugin.checkBoxList.get(targetingNode.GetNthMarkupID(targetIndex)):
          self.targetingPlugin.targetTablePlugin.checkBoxList[targetingNode.GetNthMarkupID(targetIndex)].setChecked(checkboxStatus)
      self.updateAffectiveZone()
      if not self.segmentationEditorShow3DButton.isChecked() == checked:
        self.segmentationEditorShow3DButton.checked = checked
      if self.data.segmentModelNode:
        if not self.data.segmentModelNode.GetDisplayNode().GetVisibility() == checked:
          self.data.segmentModelNode.GetDisplayNode().SetVisibility(checked)

  def updateAffectiveZone(self, caller = None, event = None):
    targetingNode = self.targetingPlugin.targetTablePlugin.currentTargets
    if self.targetingPlugin.fiducialsWidget.visible:
      targetingNode = self.targetingPlugin.fiducialsWidget.currentNode
    if self.needleModelNode and self.affectedAreaModelNode and self.approvedCoverTemplate and targetingNode.GetNumberOfFiducials():
      needleModelAppend = vtk.vtkAppendPolyData()
      affectedBallAreaAppend = vtk.vtkAppendPolyData()
      zFrameTransformMatrix = self.data.zFrameRegistrationResult.transform.GetMatrixTransformToParent()
      # The offset and ellipsoid parameters are taken from the following source code
      # http://viewvc.slicer.org/viewvc.cgi/NAMICSandBox/trunk/IGTLoadableModules/ProstateNav/TransPerinealProstateCryoTemplate/vtkMRMLTransPerinealProstateCryoTemplateNode.cxx?revision=8043&view=markup
      offsetFromTip = 5.0 #unit mm
      coneHeight = 5.0
      for targetIndex in range(targetingNode.GetNumberOfFiducials()):
        if self.displayForTargets.get(targetingNode.GetNthMarkupID(targetIndex)) == qt.Qt.Checked:
          affectedBallAreaRadius = self.GetIceBallRadius(self.needleTypeForTargets.get(targetingNode.GetNthMarkupID(targetIndex)))  # unit mm
          targetPosition = [0.0,0.0,0.0]
          targetingNode.GetNthFiducialPosition(targetIndex, targetPosition)
          (start, end, indexX, indexY, depth, inRange) = self.needlePathCaculator.computeNearestPath(targetPosition)
          needleDirection = (numpy.array(end) - numpy.array(start))/numpy.linalg.norm(numpy.array(end)-numpy.array(start))
          cone = vtk.vtkConeSource()
          cone.SetRadius(1.5)
          cone.SetResolution(6)
          cone.SetHeight(coneHeight)
          cone.CappingOff()
          cone.Update()
          transform = vtk.vtkTransform()
          transform.RotateY(-90)
          transform.RotateX(30)
          transform.Translate(-coneHeight / 2, 0.0, 0.0)
          tFilter0 = vtk.vtkTransformPolyDataFilter()
          tFilter0.SetInputData(cone.GetOutput())
          tFilter0.SetTransform(transform)
          tFilter0.Update()
          translatePart = start+depth*needleDirection
          for index, posElement in enumerate(translatePart):
            zFrameTransformMatrix.SetElement(index, 3, posElement)
          transform.SetMatrix(zFrameTransformMatrix)
          tFilter1 = vtk.vtkTransformPolyDataFilter()
          tFilter1.SetTransform(transform)
          tFilter1.SetInputData(tFilter0.GetOutput())
          tFilter1.Update()
          needleModelAppend.AddInputData(tFilter1.GetOutput())
          needleModelAppend.Update()
          pathTubeFilter = ModuleLogicMixin.createVTKTubeFilter(start, start+(depth-coneHeight)*needleDirection, radius=1.5, numSides=6)
          needleModelAppend.AddInputData(pathTubeFilter.GetOutput())
          needleModelAppend.Update()
          #End of needle model
          #--------------
          #--------------
          #Begin of affectedBallArea
          affectedBallArea = vtk.vtkParametricEllipsoid()
          affectedBallArea.SetXRadius(float(affectedBallAreaRadius[0]))
          affectedBallArea.SetYRadius(float(affectedBallAreaRadius[1]))
          affectedBallArea.SetZRadius(float(affectedBallAreaRadius[2]))
          affectedBallAreaSource = vtk.vtkParametricFunctionSource()
          affectedBallAreaSource.SetParametricFunction(affectedBallArea)
          affectedBallAreaSource.SetScalarModeToV()
          affectedBallAreaSource.Update()
          translatePart = start+(depth+offsetFromTip-float(affectedBallAreaRadius[2]))*needleDirection
          for index, posElement in enumerate(translatePart):
            zFrameTransformMatrix.SetElement(index, 3, posElement)
          transform.SetMatrix(zFrameTransformMatrix)
          tFilter2 = vtk.vtkTransformPolyDataFilter()
          tFilter2.SetTransform(transform)
          tFilter2.SetInputData(affectedBallAreaSource.GetOutput())
          tFilter2.Update()
          affectedBallAreaAppend.AddInputData(tFilter2.GetOutput())
          affectedBallAreaAppend.Update()

      self.needleModelNode.SetAndObservePolyData(needleModelAppend.GetOutput())
      self.affectedAreaModelNode.SetAndObservePolyData(affectedBallAreaAppend.GetOutput())
      ModuleLogicMixin.setNodeVisibility(self.needleModelNode, True)
      ModuleLogicMixin.setNodeVisibility(self.affectedAreaModelNode, True)
      ModuleLogicMixin.setNodeSliceIntersectionVisibility(self.needleModelNode, True)
      ModuleLogicMixin.setNodeSliceIntersectionVisibility(self.affectedAreaModelNode, True)
    pass 
  
  def setupLoadedTransform(self):
    self._zFrameRegistrationSuccessful = True
    self.steps[1].applyZFrameTransform()

  def setupLoadedTargets(self):
    if self.data.intraOpTargets:
      targets = self.data.intraOpTargets
      ModuleWidgetMixin.setFiducialNodeVisibility(targets, show=True)
      self.applyDefaultTargetDisplayNode(targets)
      self.markupsLogic.JumpSlicesToNthPointInMarkup(targets.GetID(), 0)


  def startIntraopDICOMReceiver(self):
    logging.info("Starting DICOM Receiver for intra-procedural data")
    if not self.data.completed:
      self.resetIntraopDICOMReceiver()
      self.intraopDICOMReceiver = SmartDICOMReceiver(self.intraopDICOMDirectory)
      self._observeIntraopDICOMReceiverEvents()
      self.intraopDICOMReceiver.start(not (self.trainingMode or self.data.completed))
    else:
      self.invokeEvent(SlicerDevelopmentToolboxEvents.StoppedEvent)
    self.importDICOMSeries(self.getFileList(self.intraopDICOMDirectory))
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.forceStatusChangeEventUpdate()

  def resetIntraopDICOMReceiver(self):
    self.intraopDICOMReceiver = getattr(self, "intraopDICOMReceiver", None)
    if self.intraopDICOMReceiver:
      self.intraopDICOMReceiver.stop()
      self.intraopDICOMReceiver.removeEventObservers()

  def _observeIntraopDICOMReceiverEvents(self):
    self.intraopDICOMReceiver.addEventObserver(self.intraopDICOMReceiver.IncomingDataReceiveFinishedEvent,
                                               self.onDICOMSeriesReceived)
    self.intraopDICOMReceiver.addEventObserver(SlicerDevelopmentToolboxEvents.StatusChangedEvent,
                                               self.onDICOMReceiverStatusChanged)

  @vtk.calldata_type(vtk.VTK_STRING)
  def onDICOMReceiverStatusChanged(self, caller, event, callData):
    customStatusProgressBar = CustomStatusProgressbar()
    customStatusProgressBar.text = callData
    if "Waiting" in callData:
      customStatusProgressBar.busy = True

  @vtk.calldata_type(vtk.VTK_STRING)
  def onDICOMSeriesReceived(self, caller, event, callData):
    self.importDICOMSeries(ast.literal_eval(callData))
    if self.trainingMode is True:
      self.resetIntraopDICOMReceiver()

  def importDICOMSeries(self, newFileList):
    indexer = ctk.ctkDICOMIndexer()

    newSeries = []
    for currentIndex, currentFile in enumerate(newFileList, start=1):
      self.invokeEvent(SlicerDevelopmentToolboxEvents.NewFileIndexedEvent,
                       ["Indexing file %s" % currentFile, len(newFileList), currentIndex].__str__())
      slicer.app.processEvents()
      currentFile = os.path.join(self.intraopDICOMDirectory, currentFile)
      indexer.addFile(slicer.dicomDatabase, currentFile, None)
      series = self.makeSeriesNumberDescription(currentFile)
      if series not in self.seriesList:
        if not series.split(": ")[0] == '__TAG_NOT_IN_INSTANCE__':
          self.seriesList.append(series)
          newSeries.append(series)
          self.loadableList[series] = self.createLoadableFileListForSeries(series)
    self.seriesList = sorted(self.seriesList, key=lambda s: int(s.split(": ")[0]))

    if len(newFileList):
      self.verifyPatientIDEquality(newFileList)
      self.invokeEvent(self.NewImageSeriesReceivedEvent, newSeries.__str__())

  def verifyPatientIDEquality(self, receivedFiles):
    seriesNumberPatientID = self.getAdditionalInformationForReceivedSeries(receivedFiles)
    dicomFileName = self.getPatientIDValidationSource()
    if not dicomFileName:
      return
    currentInfo = self.getPatientInformation(dicomFileName)
    currentID = currentInfo["PatientID"]
    patientName = currentInfo["PatientName"]
    for seriesNumber, receivedInfo in seriesNumberPatientID.items():
      patientID = receivedInfo["PatientID"]
      if patientID is not None and patientID != currentID:
        m = 'WARNING:\n' \
            'Current case:\n' \
            '  Patient ID: {0}\n' \
            '  Patient Name: {1}\n' \
            'Received image\n' \
            '  Patient ID: {2}\n' \
            '  Patient Name : {3}\n\n' \
            'Do you want to keep this series? '.format(currentID, patientName, patientID, receivedInfo["PatientName"])
        if not slicer.util.confirmYesNoDisplay(m, title="Patient IDs Not Matching", windowTitle="ProstateAblation"):
          self.deleteSeriesFromSeriesList(seriesNumber)

  def getPatientIDValidationSource(self):
    # TODO: For loading case purposes it would be nice to keep track which series were accepted
    if len(self.loadableList.keys()) > 1:
      keylist = self.loadableList.keys()
      keylist.sort(key=lambda x: int(x.split(": ")[0]))
      return self.loadableList[keylist[0]][0]
    else:
      return None

  def getOrCreateVolumeForSeries(self, series):
    try:
      volume = self.alreadyLoadedSeries[series]
    except KeyError:
      logging.info("Need to load volume")
      files = self.loadableList[series]
      loadables = self.scalarVolumePlugin.examine([files])
      success, volume = slicer.util.loadVolume(files[0], returnNode=True)
      volume.SetName(loadables[0].name)
      self.alreadyLoadedSeries[series] = volume
    slicer.app.processEvents()
    return volume

  def createLoadableFileListForSeries(self, series):
    seriesNumber = int(series.split(": ")[0])
    loadableList = []
    for dcm in self.getFileList(self.intraopDICOMDirectory):
      currentFile = os.path.join(self.intraopDICOMDirectory, dcm)
      if self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER) and (not self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER)  == '__TAG_NOT_IN_INSTANCE__'):
        try:
          int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
        except:
          print("nothing: %s" % self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
        currentSeriesNumber = int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
        if currentSeriesNumber and currentSeriesNumber == seriesNumber:
          loadableList.append(currentFile)
    return loadableList

  def deleteSeriesFromSeriesList(self, seriesNumber):
    for series in self.seriesList:
      currentSeriesNumber = int(series.split(": ")[0])
      if currentSeriesNumber == seriesNumber:
        self.seriesList.remove(series)
        for seriesFile in self.loadableList[series]:
          logging.debug("removing {} from filesystem".format(seriesFile))
          os.remove(seriesFile)
        del self.loadableList[series]

  def makeSeriesNumberDescription(self, dcmFile):
    seriesDescription = self.getDICOMValue(dcmFile, DICOMTAGS.SERIES_DESCRIPTION)
    seriesNumber = self.getDICOMValue(dcmFile, DICOMTAGS.SERIES_NUMBER)
    if not (seriesNumber and seriesDescription):
      raise DICOMValueError("Missing Attribute(s):\nFile: {}\nseriesNumber: {}\nseriesDescription: {}"
                            .format(dcmFile, seriesNumber, seriesDescription))
    return "{}: {}".format(seriesNumber, seriesDescription)

  def getAdditionalInformationForReceivedSeries(self, fileList):
    seriesNumberPatientID = {}
    for currentFile in [os.path.join(self.intraopDICOMDirectory, f) for f in fileList]:
      seriesNumber = int(self.getDICOMValue(currentFile, DICOMTAGS.SERIES_NUMBER))
      if seriesNumber not in seriesNumberPatientID.keys():
        seriesNumberPatientID[seriesNumber]= self.getPatientInformation(currentFile)
    return seriesNumberPatientID

  def getPatientInformation(self, currentFile):
    return {
      "PatientID": self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID),
      "PatientName": self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_NAME),
      "SeriesDescription": self.getDICOMValue(currentFile, DICOMTAGS.SERIES_DESCRIPTION)}

  def getSeriesForSubstring(self, substring):
    for series in reversed(self.seriesList):
      if substring in series:
        return series
    return None

  def loadCaseData(self):
    if not os.path.exists(os.path.join(self.outputDirectory, constants.JSON_FILENAME)):
      if len(os.listdir(self.intraopDICOMDirectory)):
        self.startIntraopDICOMReceiver()
    else:
      self.openSavedSession()

  def openSavedSession(self):
    self.load()

  def applyDefaultTargetDisplayNode(self, targetNode, new=False):
    displayNode = None if new else targetNode.GetDisplayNode()
    modifiedDisplayNode = self.setupDisplayNode(displayNode, True)
    targetNode.SetAndObserveDisplayNodeID(modifiedDisplayNode.GetID())

  def setupDisplayNode(self, displayNode=None, starBurst=False):
    if not displayNode:
      displayNode = slicer.vtkMRMLMarkupsDisplayNode()
      slicer.mrmlScene.AddNode(displayNode)
    displayNode.SetTextScale(0)
    displayNode.SetGlyphScale(2.5)
    if starBurst:
      displayNode.SetGlyphType(slicer.vtkMRMLAnnotationPointDisplayNode.StarBurst2D)
    return displayNode

  def loadProcessedData(self, directory):
    resourcesDir = os.path.join(directory, 'RESOURCES')
    logging.debug(resourcesDir)
    if not os.path.exists(resourcesDir):
      message = "The selected directory does not fit the directory structure. Make sure that you select the " \
                "study root directory which includes directories RESOURCES"
      return message
    seriesMap =[]
    self.loadImageAndLabel(seriesMap)
    if self.segmentationPath is None:
      message = "No segmentations found.\nMake sure that you used segment editor for segmenting the prostate first and using " \
                "its output as the data input here."
      return message
    return None

  def loadImageAndLabel(self, seriesMap):
    self.imagePath = None
    self.segmentationPath = None
    segmentedColorName = self.getSetting("Segmentation_Color_Name")

    for series in seriesMap:
      seriesName = str(seriesMap[series]['LongName'])
      logging.debug('series Number ' + series + ' ' + seriesName)

      imagePath = os.path.join(seriesMap[series]['NRRDLocation'])
      segmentationPath = os.path.dirname(os.path.dirname(imagePath))
      segmentationPath = os.path.join(segmentationPath, 'Segmentations')

      if not os.path.exists(segmentationPath):
        continue
      else:
        if any(segmentedColorName in name for name in os.listdir(segmentationPath)):
          logging.debug(' FOUND THE SERIES OF INTEREST, ITS ' + seriesName)
          logging.debug(' LOCATION OF VOLUME : ' + str(seriesMap[series]['NRRDLocation']))
          logging.debug(' LOCATION OF IMAGE path : ' + str(imagePath))

          logging.debug(' LOCATION OF SEGMENTATION path : ' + segmentationPath)

          self.imagePath = seriesMap[series]['NRRDLocation']
          self.segmentationPath = segmentationPath
          break

  def isTrackingPossible(self, series):
    if self.data.completed:
      logging.debug("No tracking possible. Case has been marked as completed!")
      return False
    else:
      return True

  def isEligibleForDistanceMeasure(self, series):
    seriesType = self.seriesTypeManager.getSeriesType(series)
    listItems = [str(item) for item in self.getSetting("COVER_PROSTATE") + self.getSetting("COVER_TEMPLATE") + self.getSetting("VIBE_IMAGE")]
    return self.isAnyListItemInString(seriesType, listItems)

  def isLoading(self):
    self._loading = getattr(self, "_loading", False)
    return self._loading

  def GetIceBallRadius(self, type):
    if type == self.ISRODTYPE:
      return numpy.array(self.getSetting("NeedleRadius_ICEROD").split())
    elif type == self.ISSEEDTYPE:
      return numpy.array(self.getSetting("NeedleRadius_ICESEED").split())
    else:
      needleRadius = numpy.array([0,0,0])
      return needleRadius

  def takeActionForCurrentSeries(self, event = None):
    callData = None
    if self.seriesTypeManager.isCoverTemplate(self.currentSeries):
      event = self.InitiateZFrameCalibrationEvent
    else:
      if self.zFrameRegistrationSuccessful:
        if self.seriesTypeManager.isCoverProstate(self.currentSeries):
          event = self.InitiateTargetingEvent
        elif self.seriesTypeManager.isGuidance(self.currentSeries):
          event = self.NeedleGuidanceEvent
        else:
          event = self.NeedleGuidanceEvent
      else:
        slicer.util.warningDisplay("ZFrame registration was not performed yet, it is required!")
    if event:
      self.invokeEvent(event, callData)
    else:
      raise UnknownSeriesError("Action for currently selected series unknown")

  @onReturnProcessEvents
  def updateProgressBar(self, **kwargs):
    if self.progress:
      for key, value in kwargs.items():
        if hasattr(self.progress, key):
          setattr(self.progress, key, value)
