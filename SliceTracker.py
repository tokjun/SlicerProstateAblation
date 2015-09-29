import os
import math, re
from __main__ import vtk, qt, ctk, slicer
from slicer.ScriptedLoadableModule import *
from Editor import EditorWidget
import EditorLib
import logging


class DICOMTAGS:

  PATIENT_NAME          = '0010,0010'
  PATIENT_ID            = '0010,0020'
  PATIENT_BIRTH_DATE    = '0010,0030'
  SERIES_DESCRIPTION    = '0008,103E'
  STUDY_DATE            = '0008,0020'
  STUDY_TIME            = '0008,0030'
  ACQUISITION_TIME      = '0008,0032'


class SliceTracker(ScriptedLoadableModule):

  def __init__(self, parent):
    ScriptedLoadableModule.__init__(self, parent)
    self.parent.title = "SliceTracker"
    self.parent.categories = ["Radiology"]
    self.parent.dependencies = []
    self.parent.contributors = ["Peter Behringer (SPL), Christian Herz (SPL), Andriy Fedorov (SPL)"]
    self.parent.helpText = """ SliceTracker facilitates support of MRI-guided targeted prostate biopsy. """
    self.parent.acknowledgementText = """Surgical Planning Laboratory, Brigham and Women's Hospital, Harvard
                                          Medical School, Boston, USA This work was supported in part by the National
                                          Institutes of Health through grants U24 CA180918,
                                          R01 CA111288 and P41 EB015898."""


class SliceTrackerWidget(ScriptedLoadableModuleWidget):
  """Uses ScriptedLoadableModuleWidget base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  STYLE_GRAY_BACKGROUND_WHITE_FONT  = 'background-color: rgb(130,130,130); ' \
                                      'color: rgb(255,255,255)'
  STYLE_WHITE_BACKGROUND            = 'background-color: rgb(255,255,255)'
  STYLE_LIGHT_GRAY_BACKGROUND       = 'background-color: rgb(230,230,230)'
  STYLE_ORANGE_BACKGROUND           = 'background-color: rgb(255,102,0)'

  @staticmethod
  def makeProgressIndicator(maxVal, initialValue=0):
    progressIndicator = qt.QProgressDialog()
    progressIndicator.minimumDuration = 0
    progressIndicator.modal = True
    progressIndicator.setMaximum(maxVal)
    progressIndicator.setValue(initialValue)
    progressIndicator.setWindowTitle("Processing...")
    progressIndicator.show()
    progressIndicator.autoClose = False
    return progressIndicator

  @staticmethod
  def createDirectory(directory, message=None):
    if message:
      logging.debug(message)
    try:
      os.makedirs(directory)
    except OSError:
      logging.debug('Failed to create the following directory: ' + directory)

  @staticmethod
  def confirmDialog(message, title='SliceTracker'):
    result = qt.QMessageBox.question(slicer.util.mainWindow(), title, message,
                                     qt.QMessageBox.Ok | qt.QMessageBox.Cancel)
    return result == qt.QMessageBox.Ok

  @staticmethod
  def notificationDialog(message, title='SliceTracker'):
    return qt.QMessageBox.information(slicer.util.mainWindow(), title, message)

  @staticmethod
  def yesNoDialog(message, title='SliceTracker'):
    result = qt.QMessageBox.question(slicer.util.mainWindow(), title, message,
                                     qt.QMessageBox.Yes | qt.QMessageBox.No)
    return result == qt.QMessageBox.Yes

  @staticmethod
  def warningDialog(message, title='SliceTracker'):
    return qt.QMessageBox.warning(slicer.util.mainWindow(), title, message)

  def __init__(self, parent = None):
    ScriptedLoadableModuleWidget.__init__(self, parent)
    assert slicer.dicomDatabase
    self.dicomDatabase = slicer.dicomDatabase
    self.logic = SliceTrackerLogic()
    self.layoutManager = slicer.app.layoutManager()
    self.markupsLogic = slicer.modules.markups.logic()
    self.volumesLogic = slicer.modules.volumes.logic()
    self.modulePath = slicer.modules.slicetracker.path.replace(self.moduleName+".py","")
    self.iconPath = os.path.join(self.modulePath, 'Resources/Icons')

  def onReload(self):
    ScriptedLoadableModuleWidget.onReload(self)
    slicer.mrmlScene.Clear(0)
    self.biasCorrectionDone = False
    self.logic = SliceTrackerLogic()

  def getSetting(self, settingName):
    settings = qt.QSettings()
    return str(settings.value(self.moduleName + '/' + settingName))

  def setSetting(self, settingName, value):
    settings = qt.QSettings()
    settings.setValue(self.moduleName + '/' + settingName, value)

  def createPatientWatchBox(self):
    self.patientViewBox = qt.QGroupBox()
    self.patientViewBox.setStyleSheet(self.STYLE_LIGHT_GRAY_BACKGROUND)
    self.patientViewBox.setFixedHeight(90)
    self.patientViewBoxLayout = qt.QGridLayout()
    self.patientViewBox.setLayout(self.patientViewBoxLayout)
    self.patientViewBoxLayout.setColumnMinimumWidth(1, 50)
    self.patientViewBoxLayout.setColumnMinimumWidth(2, 50)
    self.patientViewBoxLayout.setHorizontalSpacing(0)
    self.layout.addWidget(self.patientViewBox)
    # create patient attributes
    self.categoryPatientID = qt.QLabel('Patient ID: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientID, 1, 1)
    self.categoryPatientName = qt.QLabel('Patient Name: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientName, 2, 1)
    self.categoryPatientBirthDate = qt.QLabel('Date of Birth: ')
    self.patientViewBoxLayout.addWidget(self.categoryPatientBirthDate, 3, 1)
    self.categoryPreopStudyDate = qt.QLabel('Preop Study Date:')
    self.patientViewBoxLayout.addWidget(self.categoryPreopStudyDate, 4, 1)
    self.categoryCurrentStudyDate = qt.QLabel('Current Study Date:')
    self.patientViewBoxLayout.addWidget(self.categoryCurrentStudyDate, 5, 1)
    self.patientID = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientID, 1, 2)
    self.patientName = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientName, 2, 2)
    self.patientBirthDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.patientBirthDate, 3, 2)
    self.preopStudyDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.preopStudyDate, 4, 2)
    self.currentStudyDate = qt.QLabel('None')
    self.patientViewBoxLayout.addWidget(self.currentStudyDate, 5, 2)

  def createIcon(self, filename):
    path = os.path.join(self.iconPath, filename)
    pixmap = qt.QPixmap(path)
    return qt.QIcon(pixmap)

  def createButton(self, title, **kwargs):
    button = qt.QPushButton(title)
    for key, value in kwargs.iteritems():
      if hasattr(button, key):
        setattr(button, key, value)
      else:
        logging.error("QPushButton does not have attribute %s" % key)
    return button

  def createComboBox(self, **kwargs):
    combobox = slicer.qMRMLNodeComboBox()
    combobox.addEnabled = False
    combobox.removeEnabled = False
    combobox.noneEnabled = True
    combobox.showHidden = False
    for key, value in kwargs.iteritems():
      if hasattr(combobox, key):
        setattr(combobox, key, value)
      else:
        logging.error("qMRMLNodeComboBox does not have attribute %s" % key)
    combobox.setMRMLScene(slicer.mrmlScene)
    return combobox

  def setupIcons(self):
    self.labelSegmentationIcon = self.createIcon('icon-labelSegmentation.png')
    self.applySegmentationIcon = self.createIcon('icon-applySegmentation.png')
    self.greenCheckIcon = self.createIcon('icon-greenCheck.png')
    self.quickSegmentationIcon = self.createIcon('icon-quickSegmentation.png')
    self.folderIcon = self.createIcon('icon-folder.png')
    self.dataSelectionIcon = self.createIcon('icon-dataselection_fit.png')
    self.labelSelectionIcon = self.createIcon('icon-labelselection_fit.png')
    self.registrationSectionIcon = self.createIcon('icon-registration_fit.png')
    self.evaluationSectionIcon = self.createIcon('icon-evaluation_fit.png')
    self.newImageDataIcon = self.createIcon('icon-newImageData.png')
    self.littleDiscIcon = self.createIcon('icon-littleDisc.png')

  def createTabWidget(self):
    self.tabWidget = qt.QTabWidget()
    self.layout.addWidget(self.tabWidget)
    # get the TabBar
    self.tabBar = self.tabWidget.childAt(1, 1)
    # create Widgets inside each tab
    self.dataSelectionGroupBox = qt.QGroupBox()
    self.labelSelectionGroupBox = qt.QGroupBox()
    self.registrationGroupBox = qt.QGroupBox()
    self.evaluationGroupBox = qt.QGroupBox()
    self.tabWidget.setIconSize(qt.QSize(110, 50))
    # create Layout for each groupBox
    self.dataSelectionGroupBoxLayout = qt.QFormLayout()
    self.labelSelectionGroupBoxLayout = qt.QFormLayout()
    self.registrationGroupBoxLayout = qt.QFormLayout()
    self.evaluationGroupBoxLayout = qt.QFormLayout()
    # set Layout
    self.dataSelectionGroupBox.setLayout(self.dataSelectionGroupBoxLayout)
    self.labelSelectionGroupBox.setLayout(self.labelSelectionGroupBoxLayout)
    self.registrationGroupBox.setLayout(self.registrationGroupBoxLayout)
    self.evaluationGroupBox.setLayout(self.evaluationGroupBoxLayout)
    # add Tabs
    self.tabWidget.addTab(self.dataSelectionGroupBox, self.dataSelectionIcon, '')
    self.tabWidget.addTab(self.labelSelectionGroupBox, self.labelSelectionIcon, '')
    self.tabWidget.addTab(self.registrationGroupBox, self.registrationSectionIcon, '')
    self.tabWidget.addTab(self.evaluationGroupBox, self.evaluationSectionIcon, '')

  def createIncomeSimulationButtons(self):
    self.simDataIncomeButton2 = self.createButton("Simulate Data Income 1", styleSheet=self.STYLE_ORANGE_BACKGROUND,
                                                  toolTip="Localizer, COVER TEMPLATE, NEEDLE GUIDANCE 3")
    self.dataSelectionGroupBoxLayout.addWidget(self.simDataIncomeButton2)

    self.simDataIncomeButton3 = self.createButton("Simulate Data Income 2", styleSheet=self.STYLE_ORANGE_BACKGROUND)
    self.dataSelectionGroupBoxLayout.addWidget(self.simDataIncomeButton3)

    self.simDataIncomeButton4 = self.createButton("Simulate Data Income 3", styleSheet=self.STYLE_ORANGE_BACKGROUND)
    self.dataSelectionGroupBoxLayout.addWidget(self.simDataIncomeButton4)

    self.showSimulationButtons(showButtons=False)

  def showSimulationButtons(self, showButtons=True):
    for button in [self.simDataIncomeButton2, self.simDataIncomeButton3, self.simDataIncomeButton4]:
      button.show() if showButtons else button.hide()
    if showButtons:
      self.simDataIncomeButton2.connect('clicked(bool)',self.onSimulateDataIncomeButton2)
      self.simDataIncomeButton3.connect('clicked(bool)',self.onSimulateDataIncomeButton3)
      self.simDataIncomeButton4.connect('clicked(bool)',self.onSimulateDataIncomeButton4)

  def setup(self):
    ScriptedLoadableModuleWidget.setup(self)

    try:
      import VolumeClipWithModel
    except ImportError:
      return self.warningDialog("Error: Could not find extension VolumeClip. Open Slicer Extension Manager and install "
                                "VolumeClip.", "Missing Extension")

    self.currentIntraopVolume = None
    self.currentIntraopLabel = None

    self.preopVolume = None
    self.preopLabel = None
    self.preopTargets = None

    self.seriesItems = []
    self.revealCursor = None

    self.quickSegmentationActive = False
    self.comingFromPreopTag = False
    self.biasCorrectionDone = False

    self.outputTargets = dict()
    self.outputVolumes = dict()
    self.outputTransforms = dict()

    self.reRegistrationMode = False
    self.registrationResults = []
    self.selectableRegistrationResults = []

    self.createPatientWatchBox()
    self.setupIcons()
    self.createTabWidget()

    self.setupSliceWidgets()
    self.setupDataSelectionStep()
    self.setupProstateSegmentationStep()
    self.setupRegistrationStep()
    self.setupRegistrationEvaluationStep()

    self.setupConnections()

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)
    self.setAxialOrientation()

    self.setTabsEnabled([1, 2, 3], False)

    self.onTab1clicked()
    self.logic.setupColorTable()
    self.removeSliceAnnotations()

  def setupSliceWidgets(self):
    self.setupRedSliceWidget()
    self.setupYellowSliceWidget()
    self.setupGreenSliceWidget()

  def setupRedSliceWidget(self):
    self.redWidget = self.layoutManager.sliceWidget('Red')
    self.compositeNodeRed = self.redWidget.mrmlSliceCompositeNode()
    self.redSliceLogic = self.redWidget.sliceLogic()
    self.redSliceView = self.redWidget.sliceView()
    self.redSliceNode = self.redSliceLogic.GetSliceNode()
    self.currentFOVRed = []

  def setupYellowSliceWidget(self):
    self.yellowWidget = self.layoutManager.sliceWidget('Yellow')
    self.compositeNodeYellow = self.yellowWidget.mrmlSliceCompositeNode()
    self.yellowSliceLogic = self.yellowWidget.sliceLogic()
    self.yellowSliceView = self.yellowWidget.sliceView()
    self.yellowSliceNode = self.yellowSliceLogic.GetSliceNode()
    self.currentFOVYellow = []

  def setupGreenSliceWidget(self):
    self.greenWidget = self.layoutManager.sliceWidget('Green')
    self.compositeNodeGreen = self.greenWidget.mrmlSliceCompositeNode()
    self.greenSliceLogic = self.greenWidget.sliceLogic()
    self.greenSliceNode = self.greenSliceLogic.GetSliceNode()

  def setStandardOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToSagittal()
    self.greenSliceNode.SetOrientationToCoronal()

  def setAxialOrientation(self):
    self.redSliceNode.SetOrientationToAxial()
    self.yellowSliceNode.SetOrientationToAxial()
    self.greenSliceNode.SetOrientationToAxial()

  def setupDataSelectionStep(self):
    self.preopDataDir = ""
    self.preopDirButton = self.createButton('choose directory', icon=self.folderIcon)
    self.dataSelectionGroupBoxLayout.addRow("Preop directory:", self.preopDirButton)

    self.outputDir = self.getSetting('OutputLocation')
    self.outputDirButton = self.createButton(self.shortenDirText(self.outputDir), icon=self.folderIcon)
    self.dataSelectionGroupBoxLayout.addRow("Output directory:", self.outputDirButton)

    self.intraopDataDir = ""
    self.intraopDirButton = self.createButton('choose directory', icon=self.folderIcon, enabled=False)
    self.dataSelectionGroupBoxLayout.addRow("Intraop directory:", self.intraopDirButton)

    self.intraopSeriesSelector = ctk.ctkCollapsibleGroupBox()
    self.intraopSeriesSelector.setTitle("Intraop series")
    self.dataSelectionGroupBoxLayout.addRow(self.intraopSeriesSelector)
    intraopSeriesSelectorLayout = qt.QFormLayout(self.intraopSeriesSelector)

    self.seriesView = qt.QListView()
    self.seriesView.setObjectName('SeriesTable')
    self.seriesView.setSpacing(3)
    self.seriesModel = qt.QStandardItemModel()
    self.seriesModel.setHorizontalHeaderLabels(['Series ID'])
    self.seriesView.setModel(self.seriesModel)
    self.seriesView.setSelectionMode(qt.QAbstractItemView.ExtendedSelection)
    self.seriesView.setEditTriggers(qt.QAbstractItemView.NoEditTriggers)
    intraopSeriesSelectorLayout.addWidget(self.seriesView)

    row = qt.QWidget()
    rowLayout = self.createAlignedRowLayout(row, alignment=qt.Qt.AlignRight)

    self.loadAndSegmentButton = self.createButton("Load and Segment", enabled=False, toolTip="Load and Segment")
    rowLayout.addWidget(self.loadAndSegmentButton)

    self.createIncomeSimulationButtons()

    self.reRegButton = self.createButton("Re-Registration", toolTip="Re-Registration", enabled=False,
                                         styleSheet=self.STYLE_WHITE_BACKGROUND)
    rowLayout.addWidget(self.reRegButton)
    self.dataSelectionGroupBoxLayout.addWidget(row)

  def setupProstateSegmentationStep(self):
    self.labelSelectionCollapsibleButton = ctk.ctkCollapsibleButton()
    self.labelSelectionCollapsibleButton.text = "Step 2: Label Selection"
    self.labelSelectionCollapsibleButton.collapsed = 0
    self.labelSelectionCollapsibleButton.hide()
    self.layout.addWidget(self.labelSelectionCollapsibleButton)

    firstRow = qt.QWidget()
    rowLayout = qt.QHBoxLayout()
    firstRow.setLayout(rowLayout)

    self.text = qt.QLabel('Reference Volume: ')
    rowLayout.addWidget(self.text)

    # reference volume selector
    self.referenceVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                       selectNodeUponCreation=True, showChildNodeTypes=False,
                                                       toolTip="Pick the input to the algorithm.")
    rowLayout.addWidget(self.referenceVolumeSelector)
    # set info box

    self.helperLabel = qt.QLabel()
    helperPixmap = qt.QPixmap(os.path.join(self.iconPath, 'icon-infoBox.png'))
    helperPixmap = helperPixmap.scaled(qt.QSize(20, 20))
    self.helperLabel.setPixmap(helperPixmap)
    self.helperLabel.setToolTip('This is the information you needed, right?')

    rowLayout.addWidget(self.helperLabel)

    self.labelSelectionGroupBoxLayout.addRow(firstRow)

    # Set Icon Size for the 4 Icon Items
    size = qt.QSize(40, 40)
    self.quickSegmentationButton = self.createButton('Quick Mode', icon=self.quickSegmentationIcon, iconSize=size,
                                                     styleSheet=self.STYLE_WHITE_BACKGROUND)
    self.quickSegmentationButton.setFixedHeight(50)

    self.labelSegmentationButton = self.createButton('Label Mode', icon=self.labelSegmentationIcon, iconSize=size,
                                                     styleSheet=self.STYLE_WHITE_BACKGROUND)
    self.labelSegmentationButton.setFixedHeight(50)

    self.applySegmentationButton = self.createButton("", icon=self.applySegmentationIcon, iconSize=size,
                                                     styleSheet=self.STYLE_WHITE_BACKGROUND, enabled=False)
    self.applySegmentationButton.setFixedHeight(50)

    self.forwardButton = qt.QPushButton('Step forward')
    self.forwardButton.setFixedHeight(50)

    self.backButton = qt.QPushButton('Step back')
    self.backButton.setFixedHeight(50)

    self.deactivateUndoRedoButtons()

    # Create ButtonBox to fill in those Buttons
    buttonBox1 = qt.QDialogButtonBox()
    buttonBox1.setLayoutDirection(1)
    buttonBox1.centerButtons = False
    buttonBox1.addButton(self.forwardButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.backButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.applySegmentationButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.quickSegmentationButton, buttonBox1.ActionRole)
    buttonBox1.addButton(self.labelSegmentationButton, buttonBox1.ActionRole)
    self.labelSelectionGroupBoxLayout.addWidget(buttonBox1)

    # Editor Widget
    editorWidgetParent = slicer.qMRMLWidget()
    editorWidgetParent.setLayout(qt.QVBoxLayout())
    editorWidgetParent.setMRMLScene(slicer.mrmlScene)

    self.editUtil = EditorLib.EditUtil.EditUtil()
    self.editorWidget = EditorWidget(parent=editorWidgetParent, showVolumesFrame=False)
    self.editorWidget.setup()
    self.editorParameterNode = self.editUtil.getParameterNode()
    self.labelSelectionGroupBoxLayout.addRow(editorWidgetParent)

  def setupRegistrationStep(self):
    self.preopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], showChildNodeTypes=False,
                                                   selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Preop Image Volume: ", self.preopVolumeSelector)

    self.preopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""], showChildNodeTypes=False,
                                                  selectNodeUponCreation=False, toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Preop Label Volume: ", self.preopLabelSelector)

    self.intraopVolumeSelector = self.createComboBox(nodeTypes=["vtkMRMLScalarVolumeNode", ""], noneEnabled=True,
                                                     showChildNodeTypes=False, selectNodeUponCreation=True,
                                                     toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Intraop Image Volume: ", self.intraopVolumeSelector)
    self.intraopLabelSelector = self.createComboBox(nodeTypes=["vtkMRMLLabelMapVolumeNode", ""],
                                                    showChildNodeTypes=False,
                                                    selectNodeUponCreation=True, toolTip="Pick algorithm input.")
    self.registrationGroupBoxLayout.addRow("Intraop Label Volume: ", self.intraopLabelSelector)

    self.fiducialSelector = self.createComboBox(nodeTypes=["vtkMRMLMarkupsFiducialNode", ""], noneEnabled=True,
                                                showChildNodeTypes=False, selectNodeUponCreation=False,
                                                toolTip="Select the Targets")
    self.registrationGroupBoxLayout.addRow("Targets: ", self.fiducialSelector)

    self.applyBSplineRegistrationButton = self.createButton("Apply Registration", icon=self.greenCheckIcon,
                                                            toolTip="Run the algorithm.")
    self.applyBSplineRegistrationButton.setFixedHeight(45)
    self.registrationGroupBoxLayout.addRow(self.applyBSplineRegistrationButton)

  def setupRegistrationEvaluationStep(self):
    # Buttons which registration step should be shown
    selectPatientRowLayout = qt.QHBoxLayout()

    firstRow = qt.QWidget()
    rowLayout = self.createAlignedRowLayout(firstRow, alignment=qt.Qt.AlignLeft)

    self.text = qt.QLabel('Registration Result')
    rowLayout.addWidget(self.text)

    self.resultSelector = ctk.ctkComboBox()
    self.resultSelector.setFixedWidth(250)
    rowLayout.addWidget(self.resultSelector)

    self.showPreopResultButton = self.createButton('Show Preop')
    self.showRigidResultButton = self.createButton('Show Rigid Result')
    self.showAffineResultButton = self.createButton('Show Affine Result')
    self.showBSplineResultButton = self.createButton('Show BSpline Result')

    self.registrationButtonGroup = qt.QButtonGroup()
    self.registrationButtonGroup.addButton(self.showPreopResultButton, 1)
    self.registrationButtonGroup.addButton(self.showRigidResultButton, 2)
    self.registrationButtonGroup.addButton(self.showAffineResultButton, 3)
    self.registrationButtonGroup.addButton(self.showBSplineResultButton, 4)

    biggerWidget = qt.QWidget()
    twoRowLayout = qt.QVBoxLayout()
    biggerWidget.setLayout(twoRowLayout)

    twoRowLayout.addWidget(firstRow)

    secondRow = qt.QWidget()
    rowLayout = qt.QHBoxLayout()
    secondRow.setLayout(rowLayout)
    rowLayout.addWidget(self.showPreopResultButton)
    rowLayout.addWidget(self.showRigidResultButton)
    rowLayout.addWidget(self.showAffineResultButton)
    rowLayout.addWidget(self.showBSplineResultButton)
    twoRowLayout.addWidget(secondRow)

    selectPatientRowLayout.addWidget(biggerWidget)

    self.groupBoxDisplay = qt.QGroupBox("Display")
    self.groupBoxDisplayLayout = qt.QFormLayout(self.groupBoxDisplay)
    self.groupBoxDisplayLayout.addRow(selectPatientRowLayout)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxDisplay)

    fadeHolder = qt.QWidget()
    fadeLayout = qt.QHBoxLayout()
    fadeHolder.setLayout(fadeLayout)

    self.visualEffectsGroupBox = qt.QGroupBox("Visual Evaluation")
    self.groupBoxLayout = qt.QFormLayout(self.visualEffectsGroupBox)
    self.evaluationGroupBoxLayout.addWidget(self.visualEffectsGroupBox)

    self.fadeSlider = ctk.ctkSliderWidget()
    self.fadeSlider.minimum = 0
    self.fadeSlider.maximum = 1.0
    self.fadeSlider.value = 0
    self.fadeSlider.singleStep = 0.05
    fadeLayout.addWidget(self.fadeSlider)

    animaHolder = qt.QWidget()
    animaLayout = qt.QVBoxLayout()
    animaHolder.setLayout(animaLayout)
    fadeLayout.addWidget(animaHolder)

    self.rockCount = 0
    self.rockTimer = qt.QTimer()
    self.rockCheckBox = qt.QCheckBox("Rock")
    self.rockCheckBox.checked = False
    animaLayout.addWidget(self.rockCheckBox)

    self.flickerTimer = qt.QTimer()
    self.flickerCheckBox = qt.QCheckBox("Flicker")
    self.flickerCheckBox.checked = False
    animaLayout.addWidget(self.flickerCheckBox)

    self.groupBoxLayout.addRow("Opacity", fadeHolder)

    self.revealCursorCheckBox = qt.QCheckBox("Use RevealCursor")
    self.revealCursorCheckBox.checked = False
    self.groupBoxLayout.addRow("", self.revealCursorCheckBox)

    self.groupBoxTargets = qt.QGroupBox("Targets")
    self.groupBoxLayoutTargets = qt.QFormLayout(self.groupBoxTargets)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxTargets)

    self.targetTable = qt.QTableWidget()
    self.targetTable.setRowCount(0)
    self.targetTable.setColumnCount(3)
    self.targetTable.setColumnWidth(0, 160)
    self.targetTable.setColumnWidth(1, 180)
    self.targetTable.setColumnWidth(2, 180)
    self.targetTable.setHorizontalHeaderLabels(['Target', 'Distance to needle-tip 2D [mm]',
                                                'Distance to needle-tip 3D [mm]'])
    self.groupBoxLayoutTargets.addRow(self.targetTable)

    self.needleTipButton = qt.QPushButton('Set needle-tip')
    self.groupBoxLayoutTargets.addRow(self.needleTipButton)

    self.groupBoxOutputData = qt.QGroupBox("Data output")
    self.groupBoxOutputDataLayout = qt.QFormLayout(self.groupBoxOutputData)
    self.evaluationGroupBoxLayout.addWidget(self.groupBoxOutputData)
    self.saveDataButton = self.createButton('Save Data', icon=self.littleDiscIcon, maximumWidth=150,
                                            enabled=os.path.exists(self.getSetting('OutputLocation')))
    self.groupBoxOutputDataLayout.addWidget(self.saveDataButton)

  def setTabsEnabled(self, indexes, enabled):
    for index in indexes:
      self.tabBar.setTabEnabled(index, enabled)

  def createAlignedRowLayout(self, firstRow, alignment):
    rowLayout = qt.QHBoxLayout()
    rowLayout.setAlignment(alignment)
    firstRow.setLayout(rowLayout)
    rowLayout.setDirection(0)
    return rowLayout

  def setupConnections(self):
    self.tabWidget.connect('currentChanged(int)',self.onTabWidgetClicked)
    self.preopDirButton.connect('clicked()', self.onPreopDirSelected)
    self.intraopDirButton.connect('clicked()', self.onIntraopDirSelected)
    self.reRegButton.connect('clicked(bool)',self.onReRegistrationClicked)
    self.referenceVolumeSelector.connect('currentNodeChanged(bool)',self.onTab2clicked)
    self.forwardButton.connect('clicked(bool)',self.onForwardButtonClicked)
    self.backButton.connect('clicked(bool)',self.onBackButtonClicked)
    self.applyBSplineRegistrationButton.connect('clicked(bool)',self.onApplyRegistrationClicked)
    self.resultSelector.connect('currentIndexChanged(int)',self.onRegistrationResultSelected)
    self.fadeSlider.connect('valueChanged(double)', self.changeOpacity)
    self.rockCheckBox.connect('toggled(bool)', self.onRockToggled)
    self.flickerCheckBox.connect('toggled(bool)', self.onFlickerToggled)
    self.revealCursorCheckBox.connect('toggled(bool)', self.revealToggled)
    self.needleTipButton.connect('clicked(bool)',self.onNeedleTipButtonClicked)
    self.outputDirButton.connect('clicked()', self.onOutputDirSelected)
    self.quickSegmentationButton.connect('clicked(bool)',self.onQuickSegmentationButtonClicked)
    self.labelSegmentationButton.connect('clicked(bool)',self.onLabelSegmentationButtonClicked)
    self.applySegmentationButton.connect('clicked(bool)',self.onApplySegmentationButtonClicked)
    self.loadAndSegmentButton.connect('clicked(bool)',self.onLoadAndSegmentButtonClicked)
    self.preopVolumeSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.intraopVolumeSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.intraopLabelSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.preopLabelSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.fiducialSelector.connect('currentNodeChanged(bool)',self.onTab3clicked)
    self.rockTimer.connect('timeout()', self.onRockToggled)
    self.flickerTimer.connect('timeout()', self.onFlickerToggled)
    self.saveDataButton.connect('clicked(bool)',self.onSaveData)
    self.registrationButtonGroup.connect('buttonClicked(int)', self.onRegistrationButtonChecked)
    self.seriesModel.itemChanged.connect(self.updateSeriesSelectionButtons)

  def onRegistrationButtonChecked(self, id):
    if id == 1:
      self.onPreopResultClicked()
    elif id == 2:
      self.onRigidResultClicked()
    elif id == 3:
      self.onAffineResultClicked()
    elif id == 4:
      self.onBSplineResultClicked()

  def cleanup(self):
    ScriptedLoadableModuleWidget.cleanup(self)

  def deactivateUndoRedoButtons(self):
    self.forwardButton.setEnabled(0)
    self.backButton.setEnabled(0)

  def updateUndoRedoButtons(self, observer=None, caller=None):
    self.updateBackButton()
    self.updateForwardButton()

  def updateBackButton(self):
    if self.logic.inputMarkupNode.GetNumberOfFiducials() > 0:
      self.backButton.setEnabled(1)
    else:
      self.backButton.setEnabled(0)

  def updateForwardButton(self):
    if self.deletedMarkups.GetNumberOfFiducials() > 0:
      self.forwardButton.setEnabled(1)
    else:
      self.forwardButton.setEnabled(0)

  def startStoreSCP(self):
    # TODO: add proper communication establishment
    # command : $ sudo storescp -v -p 104
    pathToExe = os.path.join(slicer.app.slicerHome, 'bin', 'storescp')
    port = 104
    cmd = ('sudo '+pathToExe+ ' -v -p '+str(port))
    os.system(cmd)

  def onLoadAndSegmentButtonClicked(self):

    selectedSeriesList = self.getSelectedSeries()

    if len(selectedSeriesList) > 0:
      if self.reRegistrationMode:
        if not self.yesNoDialog("You are currently in the Re-Registration mode. Are you sure, that you want to "
                                "recreate the segmentation?"):
          return
      self.currentIntraopVolume = self.logic.loadSeriesIntoSlicer(selectedSeriesList, self.intraopDataDir)

      # set last inputVolume Node as Reference Volume in Label Selection
      self.referenceVolumeSelector.setCurrentNode(self.currentIntraopVolume)

      # set last inputVolume Node as Intraop Image Volume in Registration
      self.intraopVolumeSelector.setCurrentNode(self.currentIntraopVolume)

      # Fit Volume To Screen
      slicer.app.applicationLogic().FitSliceToAll()

      self.tabBar.setTabEnabled(1,True)

      # enter Label Selection Section
      self.onTab2clicked()

  def uncheckSeriesSelectionItems(self):
    for item in range(len(self.logic.seriesList)):
      self.seriesModel.item(item).setCheckState(0)
    self.updateSeriesSelectionButtons()

  def updateSeriesSelectionButtons(self):
    checkedItemCount = len(self.getSelectedSeries())
    if checkedItemCount == 0 or (self.reRegistrationMode and checkedItemCount > 1):
      self.reRegButton.setEnabled(False)
    elif self.reRegistrationMode and checkedItemCount == 1:
      self.reRegButton.setEnabled(True)
    self.loadAndSegmentButton.setEnabled(checkedItemCount != 0)

  def onReRegistrationClicked(self):
    logging.debug('Performing Re-Registration')

    selectedSeriesList = self.getSelectedSeries()

    if len(selectedSeriesList) == 1:
      self.currentIntraopVolume = self.logic.loadSeriesIntoSlicer(selectedSeriesList, self.intraopDataDir)
      self.onInvokeReRegistration()
    else:
      self.warningDialog("You need to select ONE series for doing a Re-Registration. Please repeat your selection and "
                         "press Re-Registration again.")

  def onRegistrationResultSelected(self):
    for index, result in enumerate(self.registrationResults):
      self.markupsLogic.SetAllMarkupsVisibility(result['outputTargetsRigid'], False)
      if 'outputTargetsAffine' in result.keys():
        self.markupsLogic.SetAllMarkupsVisibility(result['outputTargetsAffine'], False)
      self.markupsLogic.SetAllMarkupsVisibility(result['outputTargetsBSpline'], False)

      if result['name'] == self.resultSelector.currentText:
        self.currentRegistrationResultIndex = index

    self.currentIntraopVolume = self.registrationResults[-1]['fixedVolume']
    self.outputVolumes = self.getMostRecentVolumes()
    self.outputTargets = self.getTargetsForCurrentRegistrationResult()
    self.preopVolume = self.registrationResults[-1]['movingVolume']

    self.showAffineResultButton.setEnabled(self.resultSelector.currentText == "COVER PROSTATE")

    self.onBSplineResultClicked()

  def getMostRecentVolumes(self):
    results = self.registrationResults[-1]
    volumes = {'Rigid':results['outputVolumeRigid'], 'BSpline':results['outputVolumeBSpline']}
    if 'outputVolumeAffine' in results.keys():
      volumes['Affine'] = results['outputVolumeAffine']
    return volumes

  def getTargetsForCurrentRegistrationResult(self):
    results = self.registrationResults[self.currentRegistrationResultIndex]
    targets = {'Rigid':results['outputTargetsRigid'], 'BSpline':results['outputTargetsBSpline']}
    if 'outputTargetsAffine' in results.keys():
      targets['Affine'] = results['outputTargetsAffine']
    return targets

  def updateRegistrationResultSelector(self):
    for result in [result for result in self.registrationResults if result not in self.selectableRegistrationResults]:
      name = result['name']
      self.resultSelector.addItem(name)
      self.resultSelector.currentIndex = self.resultSelector.findText(name)
      self.selectableRegistrationResults.append(result)

  def getSeriesInfoFromXML(self, f):
    import xml.dom.minidom
    dom = xml.dom.minidom.parse(f)
    number = self.findElement(dom, 'SeriesNumber')
    name = self.findElement(dom, 'SeriesDescription')
    name = name.replace('-','')
    name = name.replace('(','')
    name = name.replace(')','')
    return number,name

  def findElement(self, dom, name):
    els = dom.getElementsByTagName('element')
    for e in els:
      if e.getAttribute('name') == name:
        return e.childNodes[0].nodeValue

  def clearTargetTable(self):

    self.needleTipButton.enabled = False

    self.targetTable.clear()
    self.targetTable.setColumnCount(3)
    self.targetTable.setColumnWidth(0,180)
    self.targetTable.setColumnWidth(1,200)
    self.targetTable.setColumnWidth(2,200)
    self.targetTable.setHorizontalHeaderLabels(['Target','Distance to needle-tip 2D [mm]',
                                                'Distance to needle-tip 3D [mm]'])

  def onNeedleTipButtonClicked(self):
    self.needleTipButton.enabled = False
    self.logic.setNeedleTipPosition()

  def updateTargetTable(self,observer,caller):

    self.needleTip_position = []
    self.target_positions = []

    # get the positions of needle Tip and Targets
    [self.needleTip_position, self.target_positions] = self.logic.getNeedleTipAndTargetsPositions()

    # get the targets
    fidNode1=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)
    number_of_targets = fidNode1.GetNumberOfFiducials()

    # set number of rows in targetTable
    self.targetTable.setRowCount(number_of_targets)
    self.target_items = []

    # refresh the targetTable
    for target in range(number_of_targets):
      target_text = fidNode1.GetNthFiducialLabel(target)
      item = qt.QTableWidgetItem(target_text)
      self.targetTable.setItem(target,0,item)
      # make sure to keep a reference to the item
      self.target_items.append(item)

    self.items_2D = []
    self.items_3D = []

    for index in range(number_of_targets):
      distances = self.logic.measureDistance(self.target_positions[index],self.needleTip_position)
      text_for_2D_column = ('x = '+str(round(distances[0],2))+' y = '+str(round(distances[1],2)))
      text_for_3D_column = str(round(distances[3],2))

      item_2D = qt.QTableWidgetItem(text_for_2D_column)
      self.targetTable.setItem(index,1,item_2D)
      self.items_2D.append(item_2D)
      logging.debug(str(text_for_2D_column))

      item_3D = qt.QTableWidgetItem(text_for_3D_column)
      self.targetTable.setItem(index,2,item_3D)
      self.items_3D.append(item_3D)
      logging.debug(str(text_for_3D_column))

    # reset needleTipButton
    self.needleTipButton.enabled = True

  def removeSliceAnnotations(self):
    try:
      self.red_renderer.RemoveActor(self.text_preop)
      self.yellow_renderer.RemoveActor(self.text_intraop)
      self.redSliceView.update()
      self.yellowSliceView.update()
    except:
      pass

  def addSliceAnnotations(self):
    # TODO: adapt when zoom is changed manually
    width = self.redSliceView.width
    renderWindow = self.redSliceView.renderWindow()
    self.red_renderer = renderWindow.GetRenderers().GetItemAsObject(0)

    self.text_preop = vtk.vtkTextActor()
    self.text_preop.SetInput('PREOP')
    textProperty = self.text_preop.GetTextProperty()
    textProperty.SetFontSize(70)
    textProperty.SetColor(1,0,0)
    textProperty.SetBold(1)
    self.text_preop.SetTextProperty(textProperty)

    #TODO: the 90px shift to the left are hard-coded right now, it would be better to
    # take the size of the vtk.vtkTextActor and shift by that size * 0.5
    # BUT -> could not find how to get vtkViewPort from sliceWidget

    self.text_preop.SetDisplayPosition(int(width*0.5-90),50)
    self.red_renderer.AddActor(self.text_preop)
    self.redSliceView.update()

    renderWindow = self.yellowSliceView.renderWindow()
    self.yellow_renderer = renderWindow.GetRenderers().GetItemAsObject(0)

    self.text_intraop = vtk.vtkTextActor()
    self.text_intraop.SetInput('INTRAOP')
    textProperty = self.text_intraop.GetTextProperty()
    textProperty.SetFontSize(70)
    textProperty.SetColor(1,0,0)
    textProperty.SetBold(1)
    self.text_intraop.SetTextProperty(textProperty)
    self.text_intraop.SetDisplayPosition(int(width*0.5-140),50)
    self.yellow_renderer.AddActor(self.text_intraop)
    self.yellowSliceView.update()

  def onForwardButtonClicked(self):
    numberOfDeletedTargets = self.deletedMarkups.GetNumberOfFiducials()
    logging.debug(('numberOfTargets in deletedMarkups is'+str(numberOfDeletedTargets)))
    pos = [0.0,0.0,0.0]

    if numberOfDeletedTargets > 0:
      self.deletedMarkups.GetNthFiducialPosition(numberOfDeletedTargets-1,pos)

    logging.debug(('deletedMarkups.position = '+str(pos)))

    if pos == [0.0,0.0,0.0]:
      logging.debug('pos was 0,0,0 -> go on')
    else:
      self.logic.inputMarkupNode.AddFiducialFromArray(pos)

      # delete it in deletedMarkups
      self.deletedMarkups.RemoveMarkup(numberOfDeletedTargets-1)

    self.updateUndoRedoButtons()

  def onBackButtonClicked(self):
    activeFiducials = self.logic.inputMarkupNode
    numberOfTargets = activeFiducials.GetNumberOfFiducials()
    logging.debug('numberOfTargets is'+str(numberOfTargets))
    pos = [0.0,0.0,0.0]
    activeFiducials.GetNthFiducialPosition(numberOfTargets-1,pos)
    logging.debug('activeFiducials.position = '+str(pos))

    if numberOfTargets > 0:
      self.deletedMarkups.GetNthFiducialPosition(numberOfTargets-1,pos)

    activeFiducials.GetNthFiducialPosition(numberOfTargets-1,pos)
    logging.debug('POS BEFORE ENTRY = '+str(pos))
    if pos == [0.0,0.0,0.0]:
      logging.debug('pos was 0,0,0 -> go on')
    else:
      # add it to deletedMarkups
      activeFiducials.GetNthFiducialPosition(numberOfTargets-1,pos)
      #logging.debug(('pos = '+str(pos))
      self.deletedMarkups.AddFiducialFromArray(pos)
      logging.debug('added Markup with position '+str(pos)+' to the deletedMarkupsList')
      # delete it in activeFiducials
      activeFiducials.RemoveMarkup(numberOfTargets-1)

    self.updateUndoRedoButtons()

  def revealToggled(self,checked):
    """Turn the RevealCursor on or off
    """
    if self.revealCursor:
      self.revealCursor.tearDown()
    if checked:
      import CompareVolumes
      self.revealCursor = CompareVolumes.LayerReveal()

  def onRockToggled(self):
    if self.rockCheckBox.checked:
      self.flickerCheckBox.setEnabled(False)
      self.rockTimer.start(50)
      self.fadeSlider.value = 0.5 + math.sin(self.rockCount / 10. ) / 2.
      self.rockCount += 1
    else:
      self.flickerCheckBox.setEnabled(True)
      self.rockTimer.stop()
      self.fadeSlider.value = 0.0

  def onFlickerToggled(self):
    if self.flickerCheckBox.checked:
      self.rockCheckBox.setEnabled(False)
      self.flickerTimer.start(300)
      self.fadeSlider.value = 1.0 if self.fadeSlider.value == 0.0 else 0.0
    else:
      self.rockCheckBox.setEnabled(True)
      self.flickerTimer.stop()
      self.fadeSlider.value = 0.0

  def onPreopDirSelected(self):
    self.preopDataDir = qt.QFileDialog.getExistingDirectory(self.parent,'Preop data directory',
                                                            self.getSetting('PreopLocation'))
    self.reRegistrationMode = False
    self.reRegButton.setEnabled(False)
    if os.path.exists(self.preopDataDir):
      self.setTabsEnabled([1,2,3], False)
      self.setSetting('PreopLocation', self.preopDataDir)
      self.preopDirButton.text = self.shortenDirText(self.preopDataDir)
      self.loadPreopData()
      self.updateSeriesSelectorTable([])

  def shortenDirText(self, directory):
    try:
      split = directory.split('/')
      splittedDir = ('.../'+str(split[-2])+'/'+str(split[-1]))
      return splittedDir
    except:
      pass

  def onIntraopDirSelected(self):
    self.intraopDataDir = qt.QFileDialog.getExistingDirectory(self.parent, 'Intraop data directory',
                                                              self.getSetting('IntraopLocation'))
    if os.path.exists(self.intraopDataDir):
      self.intraopDirButton.text = self.shortenDirText(self.intraopDataDir)
      self.setSetting('IntraopLocation', self.intraopDataDir)
      self.logic.initializeListener(self.intraopDataDir)

  def onOutputDirSelected(self):
    self.outputDir = qt.QFileDialog.getExistingDirectory(self.parent, 'Preop data directory',
                                                         self.getSetting('OutputLocation'))
    if os.path.exists(self.outputDir):
      self.outputDirButton.text = self.shortenDirText(self.outputDir)
      self.setSetting('OutputLocation', self.outputDir)
      self.saveDataButton.setEnabled(True)
    else:
      self.saveDataButton.setEnabled(False)

  def onSaveData(self):
    # TODO: if registration was redone: make a sub folder and move all initial results there

    self.successfullySavedData = []
    self.failedSaveOfData = []

    # patient_id-biopsy_DICOM_study_date-study_time
    time = qt.QTime().currentTime().toString().replace(":","")
    dirName = self.patientID.text + "-biopsy-" + self.currentStudyDate.text + time
    self.outputDirectory = os.path.join(self.outputDir, dirName, "MRgBiopsy")

    self.createDirectory(self.outputDirectory)

    self.saveIntraopSegmentation()
    self.saveBiasCorrectionResult()
    self.saveRegistrationResults()
    self.saveTipPosition()
    message = ""
    if len(self.successfullySavedData) > 0:
      message = "The following data was successfully saved:\n"
      for saved in self.successfullySavedData:
        message += saved + "\n"

    if len(self.failedSaveOfData) >0:
      message += "The following data failed to saved:\n"
      for failed in self.failedSaveOfData:
        message += failed + "\n"

    return self.notificationDialog(message)

  def saveTipPosition(self):
    # TODO
    # if user clicked on the tip position - save that as well, prefixed with the series number
    pass

  def saveData(self, node, extension, name=None):
    try:
      name = name if name else node.GetName()
      filename = os.path.join(self.outputDirectory, name + extension )
      success = slicer.util.saveNode(node, filename)
      listToAdd = self.successfullySavedData if success else self.failedSaveOfData
      listToAdd.append(node.GetName())
    except AttributeError:
      self.failedSaveOfData.append(name)

  def saveIntraopSegmentation(self):
    self.saveData(self.currentIntraopLabel, '.nrrd', name="IntraopSegmentationLabel")
    self.saveData(self.preopTargets, '.fcsv', name="PreopTargets")
    self.saveData(self.logic.clippingModelNode, '.vtk', name="IntraopSegmentationSurfaceModel")

  def saveBiasCorrectionResult(self):
    if self.biasCorrectionDone:
      self.saveData(self.preopVolume, '.nrrd')

  def saveRegistrationResults(self):
    # TODO
    self.saveRegistrationCommandLineArguments()
    self.saveOutputTransformations()
    self.saveTransformedFiducials()

  def saveRegistrationCommandLineArguments(self):
    # for all registration steps:
    #   - command line or arguments (text file or json file),
    pass

  def saveOutputTransformations(self):
    pass

  def saveTransformedFiducials(self):
    # pre-fixed with series number corresponding to the fixed image during registration
    pass

  def onTabWidgetClicked(self):
    if self.tabWidget.currentIndex==0:
      self.onTab1clicked()
    if self.tabWidget.currentIndex==1:
      self.onTab2clicked()
    if self.tabWidget.currentIndex==2:
      self.onTab3clicked()
    if self.tabWidget.currentIndex==3:
      self.onTab4clicked()

  def onTab1clicked(self):
    # (re)set the standard Icon
    self.tabBar.setTabIcon(0,self.dataSelectionIcon)
    self.uncheckAndDisableVisualEffects()
    self.removeSliceAnnotations()

  def uncheckAndDisableVisualEffects(self):
    self.flickerCheckBox.checked = False
    self.rockCheckBox.checked = False
    self.visualEffectsGroupBox.setEnabled(False)

  def onTab2clicked(self):
    self.tabWidget.setCurrentIndex(1)

    enableButton = 0 if self.referenceVolumeSelector.currentNode() is None else 1
    self.labelSegmentationButton.setEnabled(enableButton)
    self.quickSegmentationButton.setEnabled(enableButton)

    self.removeSliceAnnotations()

    # set Layout for segmentation
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # set current reference Volume
    self.compositeNodeRed.Reset()
    self.markupsLogic.SetAllMarkupsVisibility(self.preopTargets, False)
    self.compositeNodeRed.SetBackgroundVolumeID(self.currentIntraopVolume.GetID())

    self.setStandardOrientation()
    slicer.app.applicationLogic().FitSliceToAll()

  def onTab3clicked(self):
    self.applyBSplineRegistrationButton.setEnabled(1 if self.inputsAreSet() else 0)

  def inputsAreSet(self):
    return not (self.preopVolumeSelector.currentNode() is None and self.intraopVolumeSelector.currentNode() is None and
                self.preopLabelSelector.currentNode() is None and self.intraopLabelSelector.currentNode() is None and
                self.fiducialSelector.currentNode() is None)

  def onTab4clicked(self):
    self.addSliceAnnotations()

    self.setTabsEnabled([1, 2], False)

    # enable re-registration function
    self.reRegButton.setEnabled(1)
    self.reRegistrationMode = True

  def getDICOMValue(self, currentFile, tag, fallback=None):
    try:
      value = self.dicomDatabase.fileValue(currentFile, tag)
    except:
      value = fallback
    return value

  def updateCurrentPatientAndViewBox(self, currentFile):
    self.currentID = self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_ID)
    self.patientID.setText(self.currentID)
    self.updatePatientBirthdate(currentFile)
    self.updateCurrentStudyDate()
    self.updatePreopStudyDate(currentFile)
    self.updatePatientName(currentFile)

  def updatePreopStudyDate(self, currentFile):
    self.preopStudyDateDICOM = self.getDICOMValue(currentFile, DICOMTAGS.STUDY_DATE)
    formattedDate = self.preopStudyDateDICOM[0:4] + "-" + self.preopStudyDateDICOM[4:6] + "-" + \
                    self.preopStudyDateDICOM[6:8]
    self.preopStudyDate.setText(formattedDate)

  def updateCurrentStudyDate(self):
    currentStudyDate = qt.QDate().currentDate()
    self.currentStudyDate.setText(str(currentStudyDate))

  def updatePatientBirthdate(self, currentFile):
    currentBirthDateDICOM = self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_BIRTH_DATE)
    if currentBirthDateDICOM is None:
      self.patientBirthDate.setText('No Date found')
    else:
      # convert date of birth from 19550112 (yyyymmdd) to 1955-01-12
      currentBirthDateDICOM = str(currentBirthDateDICOM)
      self.currentBirthDate = currentBirthDateDICOM[0:4] + "-" + currentBirthDateDICOM[
                                                                 4:6] + "-" + currentBirthDateDICOM[6:8]
      self.patientBirthDate.setText(self.currentBirthDate)

  def updatePatientName(self, currentFile):
    self.currentPatientName = None
    currentPatientNameDICOM = self.getDICOMValue(currentFile, DICOMTAGS.PATIENT_NAME)
    # convert patient name from XXXX^XXXX to XXXXX, XXXXX
    if currentPatientNameDICOM:
      splitted = currentPatientNameDICOM.split('^')
      try:
        self.currentPatientName = splitted[1] + ", " + splitted[0]
      except IndexError:
        self.currentPatientName = splitted[0]
    self.patientName.setText(self.currentPatientName)

  def updateSeriesSelectorTable(self, seriesList):
    self.seriesModel.clear()
    self.seriesItems = []

    for seriesText in seriesList:
      sItem = qt.QStandardItem(seriesText)
      self.seriesItems.append(sItem)
      self.seriesModel.appendRow(sItem)
      sItem.setCheckable(1)

      if "PROSTATE" in seriesText:
        sItem.setCheckState(1)
      if "GUIDANCE" in seriesText:
        sItem.setCheckState(1)
        rowsAboveCurrentItem = int(len(seriesList) - 1)
        for item in range(rowsAboveCurrentItem):
          self.seriesModel.item(item).setCheckState(0)

    self.intraopSeriesSelector.collapsed = False
    self.updateSeriesSelectionButtons()

  def resetShowResultButtons(self, checkedButton):
    checked = self.STYLE_GRAY_BACKGROUND_WHITE_FONT
    unchecked = self.STYLE_WHITE_BACKGROUND
    for button in self.registrationButtonGroup.buttons():
      button.setStyleSheet(checked if button is checkedButton else unchecked)

  def onPreopResultClicked(self):
    self.saveCurrentSliceViewPositions()
    self.resetShowResultButtons(checkedButton=self.showPreopResultButton)

    self.uncheckAndDisableVisualEffects()
    self.unlinkImages()

    volumeNode = self.registrationResults[self.currentRegistrationResultIndex]['movingVolume']
    self.compositeNodeRed.SetBackgroundVolumeID(volumeNode.GetID())
    self.compositeNodeRed.SetForegroundVolumeID(None)

     # show preop Targets
    fiducialNode = self.registrationResults[self.currentRegistrationResultIndex]['targets']
    self.markupsLogic.SetAllMarkupsVisibility(fiducialNode, True)

    self.setDefaultFOV(self.redSliceLogic)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(fiducialNode.GetID(), 0)

    restoredSlicePositions = self.savedSlicePositions
    self.setFOV(self.yellowSliceLogic, restoredSlicePositions['yellowFOV'], restoredSlicePositions['yellowOffset'])

    self.comingFromPreopTag = True

  def setDefaultFOV(self, sliceLogic):
    sliceLogic.FitSliceToAll()
    FOV = sliceLogic.GetSliceNode().GetFieldOfView()
    self.setFOV(sliceLogic, [FOV[0] * 0.5, FOV[1] * 0.5, FOV[2]])

  def setFOV(self, sliceLogic, FOV, offset=None):
    sliceNode = sliceLogic.GetSliceNode()
    sliceLogic.StartSliceNodeInteraction(2)
    sliceNode.SetFieldOfView(FOV[0], FOV[1], FOV[2])
    if offset:
      sliceNode.SetSliceOffset(offset)
    sliceLogic.EndSliceNodeInteraction()

  def onRigidResultClicked(self):
    self.displayRegistrationResults(button=self.showRigidResultButton, registrationType='Rigid')

  def onAffineResultClicked(self):
    self.displayRegistrationResults(button=self.showAffineResultButton, registrationType='Affine')

  def onBSplineResultClicked(self):
    self.displayRegistrationResults(button=self.showBSplineResultButton, registrationType='BSpline')

  def displayRegistrationResults(self, button, registrationType):
    self.resetShowResultButtons(checkedButton=button)

    self.linkImages()
    self.setCurrentRegistrationResultSliceViews(registrationType)

    if self.comingFromPreopTag:
      self.resetSliceViews()
    else:
      self.setDefaultFOV(self.redSliceLogic)
      self.setDefaultFOV(self.yellowSliceLogic)

    self.showTargets(registrationType=registrationType)
    self.visualEffectsGroupBox.setEnabled(True)

  def unlinkImages(self):
    self._linkImages(0)

  def linkImages(self):
    self._linkImages(1)

  def _linkImages(self, link):
    self.compositeNodeRed.SetLinkedControl(link)
    self.compositeNodeYellow.SetLinkedControl(link)

  def setCurrentRegistrationResultSliceViews(self, registrationType):
    currentResult = self.registrationResults[self.currentRegistrationResultIndex]
    self.compositeNodeYellow.SetBackgroundVolumeID(currentResult['fixedVolume'].GetID())
    self.compositeNodeRed.SetForegroundVolumeID(currentResult['fixedVolume'].GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(currentResult['outputVolume'+registrationType].GetID())

  def showTargets(self, registrationType):
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargets['Rigid'],1 if registrationType == 'Rigid' else 0)
    self.markupsLogic.SetAllMarkupsVisibility(self.outputTargets['BSpline'],1 if registrationType == 'BSpline' else 0)
    if 'Affine' in self.outputTargets.keys():
      self.markupsLogic.SetAllMarkupsVisibility(self.outputTargets['Affine'],1 if registrationType == 'Affine' else 0)
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.outputTargets[registrationType].GetID(), 0)

  def resetSliceViews(self):

    restoredSliceOptions = self.savedSlicePositions

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.setFOV(self.yellowSliceLogic, restoredSliceOptions['yellowFOV'], restoredSliceOptions['yellowOffset'])
    self.setFOV(self.redSliceLogic, restoredSliceOptions['redFOV'], restoredSliceOptions['redOffset'])

    self.comingFromPreopTag = False

  def saveCurrentSliceViewPositions(self):
    self.savedSlicePositions = {'redOffset':self.redSliceNode.GetSliceOffset(),
                                'yellowOffset':self.yellowSliceNode.GetSliceOffset(),
                                'redFOV':self.redSliceNode.GetFieldOfView(),
                                'yellowFOV':self.yellowSliceNode.GetFieldOfView()}

  def onSimulateDataIncomeButton2(self):
    imagePath = os.path.join(self.modulePath, 'Resources', 'Testing', 'testData_1')
    self.simulateDataIncome(imagePath)

  def onSimulateDataIncomeButton3(self):
    imagePath = os.path.join(self.modulePath, 'Resources', 'Testing', 'testData_2')
    self.simulateDataIncome(imagePath)

  def onSimulateDataIncomeButton4(self):
    imagePath = os.path.join(self.modulePath, 'Resources', 'Testing', 'testData_4')
    self.simulateDataIncome(imagePath)

  def onSimulateDataIncomeButton5(self):
    imagePath = os.path.join(self.modulePath, 'Resources', 'Testing', 'testData_5')
    self.simulateDataIncome(imagePath)

  def simulateDataIncome(self, imagePath):
    # TODO: when module ready, remove this method
    # copy DICOM Files into intraop folder
    cmd = ('cp -a '+imagePath+'. ' + self.intraopDataDir)
    logging.debug(cmd)
    os.system(cmd)

  def configureSliceNodesForPreopData(self):
    for nodeId in ["vtkMRMLSliceNodeRed", "vtkMRMLSliceNodeYellow", "vtkMRMLSliceNodeGreen"]:
      slicer.mrmlScene.GetNodeByID(nodeId).SetUseLabelOutline(True)
    self.redSliceNode.SetOrientationToAxial()

  def getMostRecentNRRD(self):
    return self.getMostRecentFile(self.preopSegmentationPath, "nrrd")

  def getMostRecentTargetsFile(self):
    return self.getMostRecentFile(self.preopTargetsPath, "fcsv")

  def getMostRecentFile(self, path, fileType):
    assert type(fileType) is str
    files = [f for f in os.listdir(path) if f.endswith(fileType)]
    if len(files) == 0:
      return None
    mostRecent = None
    storedTimeStamp = 0
    for filename in files:
      actualFileName = filename.split(".")[0]
      timeStamp = int(actualFileName.split("-")[-1])
      if timeStamp > storedTimeStamp:
        mostRecent = filename
        storedTimeStamp = timeStamp
    return mostRecent

  def loadT2Label(self):
    mostRecentFilename = self.getMostRecentNRRD()
    success = False
    if mostRecentFilename:
      filename = os.path.join(self.preopSegmentationPath, mostRecentFilename)
      (success, self.preopLabel) = slicer.util.loadLabelVolume(filename, returnNode=True)
      if success:
        self.preopLabel.SetName('t2-label')
        displayNode = self.preopLabel.GetDisplayNode()
        displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')
        # rotate volume to plane
        for nodeId in ["vtkMRMLSliceNodeRed", "vtkMRMLSliceNodeYellow", "vtkMRMLSliceNodeGreen"]:
          slicer.mrmlScene.GetNodeByID(nodeId).RotateToVolumePlane(self.preopLabel)
        self.preopLabelSelector.setCurrentNode(self.preopLabel)
    return success

  def loadPreopVolume(self):
    (success, self.preopVolume) = slicer.util.loadVolume(self.preopImagePath, returnNode=True)
    if success:
      self.preopVolume.SetName('volume-PREOP')
      self.preopVolumeSelector.setCurrentNode(self.preopVolume)
    return success

  def loadPreopTargets(self):
    mostRecentTargets = self.getMostRecentTargetsFile()
    success = False
    if mostRecentTargets:
      filename = os.path.join(self.preopTargetsPath, mostRecentTargets)
      (success, self.preopTargets) = slicer.util.loadMarkupsFiducialList(filename, returnNode=True)
      if success:
        self.preopTargets.SetName('targets-PREOP')
    return success

  def loadDataPCAMPStyle(self):
    self.selectedStudyName = os.path.basename(self.preopDataDir)

    self.resourcesDir = os.path.join(self.preopDataDir, 'RESOURCES')
    self.preopTargetsPath = os.path.join(self.preopDataDir, 'Targets')

    if not os.path.exists(self.resourcesDir):
      self.confirmDialog("The selected directory does not fit the PCampReview directory structure. Make sure that you "
                         "select the study root directory which includes directories RESOURCES")
      return False

    self.seriesMap = {}

    self.patientInformationRetrieved = False

    for root, subdirs, files in os.walk(self.resourcesDir):
      logging.debug('Root: '+root+', files: '+str(files))
      resourceType = os.path.split(root)[1]

      logging.debug('Resource: '+resourceType)

      if resourceType == 'Reconstructions':
        for f in files:
          logging.debug('File: '+f)
          if f.endswith('.xml'):
            metaFile = os.path.join(root,f)
            logging.debug('Ends with xml: '+metaFile)
            try:
              (seriesNumber,seriesName) = self.getSeriesInfoFromXML(metaFile)
              logging.debug(str(seriesNumber)+' '+seriesName)
            except:
              logging.debug('Failed to get from XML')
              continue

            volumePath = os.path.join(root,seriesNumber+'.nrrd')
            self.seriesMap[seriesNumber] = {'MetaInfo':None, 'NRRDLocation':volumePath,'LongName':seriesName}
            self.seriesMap[seriesNumber]['ShortName'] = str(seriesNumber)+":"+seriesName
      elif resourceType == 'DICOM' and not self.patientInformationRetrieved:
        self.logic.importStudy(root)
        for f in files:
          self.updateCurrentPatientAndViewBox(os.path.join(root,f))
          self.patientInformationRetrieved = True
          break

    logging.debug('All series found: '+str(self.seriesMap.keys()))
    logging.debug('All series found: '+str(self.seriesMap.values()))

    logging.debug('******************************************************************************')

    self.preopImagePath=''
    self.preopSegmentationPath=''
    self.preopSegmentations = []

    for series in self.seriesMap:
      seriesName = str(self.seriesMap[series]['LongName'])
      logging.debug('series Number '+series + ' ' + seriesName)
      if re.search("ax", str(seriesName), re.IGNORECASE) and re.search("t2", str(seriesName), re.IGNORECASE):
        logging.debug(' FOUND THE SERIES OF INTEREST, ITS '+seriesName)
        logging.debug(' LOCATION OF VOLUME : ' +str(self.seriesMap[series]['NRRDLocation']))

        path = os.path.join(self.seriesMap[series]['NRRDLocation'])
        logging.debug(' LOCATION OF IMAGE path : '+str(path))

        segmentationPath = os.path.dirname(os.path.dirname(path))
        segmentationPath = os.path.join(segmentationPath, 'Segmentations')
        logging.debug(' LOCATION OF SEGMENTATION path : ' + segmentationPath)

        if not os.path.exists(segmentationPath):
          self.confirmDialog("No segmentations found.\nMake sure that you used PCampReview for segmenting the prostate "
                             "first and using its output as the preop data input here.")
          return False
        self.preopImagePath = self.seriesMap[series]['NRRDLocation']
        self.preopSegmentationPath = segmentationPath

        self.preopSegmentations = os.listdir(segmentationPath)

        logging.debug(str(self.preopSegmentations))

        break

    return True

  def loadPreopData(self):
    if not self.loadDataPCAMPStyle():
      return
    self.configureSliceNodesForPreopData()
    if not self.loadT2Label() or not self.loadPreopVolume() or not self.loadPreopTargets():
      self.warningDialog("Loading preop data failed.\nMake sure that the correct directory structure like PCampReview "
                         "explains is used. SliceTracker expects a volume, label and target")
      self.intraopDirButton.setEnabled(False)
      return
    else:
      self.intraopDirButton.setEnabled(True)
    if self.yesNoDialog("Was an endorectal coil used for preop image acquisition?"):
      self.preopVolume = self.logic.applyBiasCorrection(self.preopVolume, self.preopLabel)
      self.preopVolumeSelector.setCurrentNode(self.preopVolume)
      self.biasCorrectionDone = True
    logging.debug('TARGETS PREOP')
    logging.debug(self.preopTargets)

    self.markupsLogic.SetAllMarkupsVisibility(self.preopTargets,1)

    # set markups for registration
    self.fiducialSelector.setCurrentNode(self.preopTargets)

    # jump to first markup slice
    self.markupsLogic.JumpSlicesToNthPointInMarkup(self.preopTargets.GetID(),0)

    # Set Fiducial Properties
    markupsDisplayNode = self.preopTargets.GetDisplayNode()
    markupsDisplayNode.SetTextScale(1.9)
    markupsDisplayNode.SetGlyphScale(1.0)

    self.compositeNodeRed.SetLabelOpacity(1)

    # set Layout to redSliceViewOnly
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.setDefaultFOV(self.redSliceLogic)

  def patientCheckAfterImport(self, directory, fileList):
    for currentFile in fileList:
      if self.dicomDatabase.fileValue(os.path.join(directory, currentFile),DICOMTAGS.PATIENT_ID) != self.currentID:
        incomePatient = self.dicomDatabase.fileValue(os.path.join(directory, fileList[2]),DICOMTAGS.PATIENT_ID)
        if not self.yesNoDialog(message='WARNING: You selected Patient ID ' + self.currentID + ', but Patient ID ' +
                                         incomePatient + ' just arrived in the income folder.\nDo you still want to '
                                         'continue?', title="Patients Not Matching"):
          self.updateSeriesSelectorTable([])
          return
        else:
          break
    self.updateSeriesSelectorTable(self.logic.selectableSeries)

  def getSelectedSeries(self):
    checkedItems = [x for x in self.seriesItems if x.checkState()] if self.seriesItems else []
    return [x.text() for x in checkedItems]

  def onQuickSegmentationButtonClicked(self):
    self.clearCurrentLabels()
    self.setBackgroundToCurrentReferenceVolume()
    self.setQuickSegmentationModeON()

  def setBackgroundToCurrentReferenceVolume(self):
    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.compositeNodeYellow.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.compositeNodeGreen.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

  def clearCurrentLabels(self):
    self.compositeNodeRed.SetLabelVolumeID(None)
    self.compositeNodeYellow.SetLabelVolumeID(None)
    self.compositeNodeGreen.SetLabelVolumeID(None)

  def setQuickSegmentationModeON(self):
    self.quickSegmentationActive = True
    self.logic.deleteClippingData()
    self.setSegmentationButtons(segmentationActive=True)
    self.deactivateUndoRedoButtons()
    self.setupQuickModeHistory()
    self.logic.runQuickSegmentationMode()
    self.logic.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,self.updateUndoRedoButtons)

  def setupQuickModeHistory(self):
    try:
      self.deletedMarkups.Reset()
    except AttributeError:
      self.deletedMarkups = slicer.vtkMRMLMarkupsFiducialNode()
      self.deletedMarkups.SetName('deletedMarkups')

  def setQuickSegmentationModeOFF(self):
    self.quickSegmentationActive = False
    self.setSegmentationButtons(segmentationActive=False)
    self.deactivateUndoRedoButtons()
    self.resetToRegularViewMode()

  def resetToRegularViewMode(self):
    interactionNode = slicer.mrmlScene.GetNodeByID("vtkMRMLInteractionNodeSingleton")
    interactionNode.SwitchToViewTransformMode()
    interactionNode.SetPlaceModePersistence(0)

  def changeOpacity(self,value):
    self.compositeNodeRed.SetForegroundOpacity(value)

  def onApplySegmentationButtonClicked(self):
    self.setAxialOrientation()
    if self.quickSegmentationActive is True:
      self.onQuickSegmentationFinished()
    else:
      self.onLabelSegmentationFinished()

  def setSegmentationButtons(self, segmentationActive=False):
    self.quickSegmentationButton.setEnabled(not segmentationActive)
    self.labelSegmentationButton.setEnabled(not segmentationActive)
    self.applySegmentationButton.setEnabled(segmentationActive)

  def onQuickSegmentationFinished(self):
    inputVolume = self.referenceVolumeSelector.currentNode()
    continueSegmentation = False
    if self.logic.inputMarkupNode.GetNumberOfFiducials() > 3 and self.validPointsForQuickModeSet():

      labelName = self.referenceVolumeSelector.currentNode().GetName() + '-label'
      self.currentIntraopLabel = self.logic.labelMapFromClippingModel(inputVolume)
      self.currentIntraopLabel.SetName(labelName)

      displayNode = self.currentIntraopLabel.GetDisplayNode()
      displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

      self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)

      self.markupsLogic.SetAllMarkupsVisibility(self.logic.inputMarkupNode, False)
      self.logic.clippingModelNode.SetDisplayVisibility(False)
      self.setupScreenAfterSegmentation()
    else:
      if self.yesNoDialog("You need to set at least three points with an additional one situated on a distinct slice "
                          "as the algorithm input in order to be able to create a proper segmentation. This step is "
                          "essential for an efficient registration. Do you want to continue using the quick mode?"):
        continueSegmentation = True
      else:
        self.logic.deleteClippingData()
    if not continueSegmentation:
      self.setQuickSegmentationModeOFF()
      self.setSegmentationButtons(segmentationActive=False)

  def validPointsForQuickModeSet(self):
    positions = self.getMarkupSlicePositions()
    return min(positions) != max(positions)

  def getMarkupSlicePositions(self):
    markupNode = self.logic.inputMarkupNode
    nOfControlPoints = markupNode.GetNumberOfFiducials()
    positions = []
    pos = [0, 0, 0]
    for i in range(nOfControlPoints):
      markupNode.GetNthFiducialPosition(i, pos)
      positions.append(pos[2])
    return positions

  def onLabelSegmentationFinished(self):
    continueSegmentation = False
    deleteMask = False
    if self.isIntraopLabelValid():
      logic = EditorLib.DilateEffectLogic(self.editUtil.getSliceLogic())
      logic.erode(0, '4', 1)
      self.setupScreenAfterSegmentation()
    else:
      if self.yesNoDialog("You need to do a label segmentation. Do you want to continue using the label mode?"):
        continueSegmentation = True
      else:
        deleteMask = True
    if not continueSegmentation:
      self.editorParameterNode.SetParameter('effect', 'DefaultTool')
      self.setSegmentationButtons(segmentationActive=False)
      if deleteMask:
        slicer.mrmlScene.RemoveNode(self.currentIntraopLabel)

  def isIntraopLabelValid(self):
    import SimpleITK as sitk
    import sitkUtils
    labelAddress = sitkUtils.GetSlicerITKReadWriteAddress(self.currentIntraopLabel.GetName())
    labelImage = sitk.ReadImage(labelAddress)

    ls = sitk.LabelStatisticsImageFilter()
    ls.Execute(labelImage,labelImage)
    return ls.GetNumberOfLabels() == 2

  def setupScreenAfterSegmentation(self):
    self.clearCurrentLabels()

    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    # set up preop image and label
    self.compositeNodeRed.SetReferenceBackgroundVolumeID(self.preopVolume.GetID())
    self.compositeNodeRed.SetLabelVolumeID(self.preopLabel.GetID())

    # set up intraop image and label
    self.compositeNodeYellow.SetReferenceBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())
    self.compositeNodeYellow.SetLabelVolumeID(self.currentIntraopLabel.GetID())

    # rotate volume to plane
    self.redSliceNode.RotateToVolumePlane(self.preopVolume)
    self.yellowSliceNode.RotateToVolumePlane(self.currentIntraopLabel)

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.yellowSliceNode.SetFieldOfView(86, 136, 3.5)
    self.redSliceNode.SetFieldOfView(86, 136, 3.5)

    self.tabBar.setTabEnabled(2, True)
    self.tabBar.currentIndex = 2

  def onLabelSegmentationButtonClicked(self):
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    self.clearCurrentLabels()
    self.setSegmentationButtons(segmentationActive=True)
    self.compositeNodeRed.SetBackgroundVolumeID(self.referenceVolumeSelector.currentNode().GetID())

    # create new labelmap and set
    referenceVolume = self.referenceVolumeSelector.currentNode()
    self.currentIntraopLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene,referenceVolume,
                                                                         referenceVolume.GetName() + '-label')
    self.intraopLabelSelector.setCurrentNode(self.currentIntraopLabel)
    selectionNode = slicer.app.applicationLogic().GetSelectionNode()
    selectionNode.SetReferenceActiveVolumeID(referenceVolume.GetID())
    selectionNode.SetReferenceActiveLabelVolumeID(self.currentIntraopLabel.GetID())
    slicer.app.applicationLogic().PropagateVolumeSelection(50)

    # show label
    self.compositeNodeRed.SetLabelOpacity(1)

    # set color table
    logging.debug('intraopLabelID : ' + str(self.currentIntraopLabel.GetID()))

    # set color table
    displayNode = self.currentIntraopLabel.GetDisplayNode()
    displayNode.SetAndObserveColorNodeID('vtkMRMLColorTableNode1')

    parameterNode = self.editUtil.getParameterNode()
    parameterNode.SetParameter('effect','DrawEffect')

    # set label properties
    self.editUtil.setLabel(1)
    self.editUtil.setLabelOutline(1)

  def createRegistrationResult(self, params):

    # this function stores information and nodes of a single
    # registration run to be able to switch between results.

    # name = self.currentIntraopVolume.GetName()
    summary = {'name':self.logic.getRegistrationName(),
               'movingVolume':params[0],
               'fixedVolume':params[1],
               'movingLabel':params[2],
               'fixedLabel':params[3],
               'targets':params[4],
               'outputVolumeRigid':self.outputVolumes['Rigid'],
               'outputVolumeBSpline':self.outputVolumes['BSpline'],
               'outputTransformRigid':self.outputTransforms['Rigid'],
               'outputTransformBSpline':self.outputTransforms['BSpline'],
               'outputTargetsRigid':self.outputTargets['Rigid'],
               'outputTargetsBSpline':self.outputTargets['BSpline']}

    if 'Affine' in self.outputVolumes.keys():
      summary['outputVolumeAffine'] = self.outputVolumes['Affine']
      summary['outputTransformAffine'] = self.outputTransforms['Affine']
      summary['outputTargetsAffine'] = self.outputTargets['Affine']

    self.registrationResults.append(summary)

    logging.debug('# ___________________________  registration output  ________________________________')
    logging.debug(summary)
    logging.debug('# __________________________________________________________________________________')

  def onApplyRegistrationClicked(self):
    fixedVolume= self.intraopVolumeSelector.currentNode()
    fixedLabel = self.intraopLabelSelector.currentNode()
    movingLabel = self.preopLabelSelector.currentNode()
    targets = self.fiducialSelector.currentNode()

    sourceVolumeNode = self.preopVolumeSelector.currentNode()
    movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolumeNode, 'movingVolume-PREOP-INTRAOP')

    registrationOutput = self.logic.applyRegistration(fixedVolume, movingVolume, fixedLabel, movingLabel, targets)

    params = [sourceVolumeNode, fixedVolume, movingLabel, fixedLabel, targets]

    self.finalizeRegistrationStep(params, registrationOutput)

    logging.debug('Registration is done')

  def onInvokeReRegistration(self):
    # moving volume: copy last fixed volume
    sourceVolumeNode = self.registrationResults[0]['fixedVolume']
    movingVolume = self.volumesLogic.CloneVolume(slicer.mrmlScene, sourceVolumeNode, 'movingVolumeReReg')

    # get the intraop targets
    targets = self.registrationResults[0]['outputTargetsBSpline']

    # take the 'intraop label map', which is always fixed label in the very first preop-intraop registration
    originalFixedLabel = self.registrationResults[0]['fixedLabel']

    # create fixed label
    fixedLabel = self.volumesLogic.CreateAndAddLabelVolume(slicer.mrmlScene, self.currentIntraopVolume,
                                                           self.currentIntraopVolume.GetName()+'-label')

    lastRigidTfm = self.getLastRigidTransformation()
    self.logic.BRAINSResample(inputVolume=originalFixedLabel, referenceVolume=self.currentIntraopVolume,
                              outputVolume=fixedLabel, warpTransform=lastRigidTfm)

    reRegOutput = self.logic.applyReRegistration(fixedVolume=self.currentIntraopVolume, movingVolume=movingVolume,
                                                 fixedLabel=fixedLabel,targets=targets, lastRigidTfm=lastRigidTfm)

    movingLabel = None
    params = [sourceVolumeNode, self.currentIntraopVolume, movingLabel, fixedLabel, targets]

    self.finalizeRegistrationStep(params, reRegOutput)

    logging.debug(('Re-Registration is done'))

  def finalizeRegistrationStep(self, params, registrationOutput):
    self.outputVolumes = registrationOutput[0]
    self.outputTransforms = registrationOutput[1]
    self.outputTargets = registrationOutput[2]

    self.createRegistrationResult(params)

    for targetNode in self.outputTargets.values():
      slicer.mrmlScene.AddNode(targetNode)

    self.updateRegistrationResultSelector()
    self.setupScreenAfterRegistration()
    self.uncheckSeriesSelectionItems()

  def getLastRigidTransformation(self):
    if len(self.registrationResults) == 1:
      logging.debug('Resampling label with same mask')
      # last registration was preop-intraop, take the same mask
      # this is an identity transform:
      lastRigidTfm = vtk.vtkGeneralTransform()
      lastRigidTfm.Identity()
    else:
      lastRigidTfm = self.registrationResults[-1]['outputTransformRigid']
    return lastRigidTfm


  def setupScreenAfterRegistration(self):

    self.compositeNodeRed.SetForegroundVolumeID(self.currentIntraopVolume.GetID())
    self.compositeNodeRed.SetBackgroundVolumeID(self.registrationResults[-1]['outputVolumeBSpline'].GetID())
    self.compositeNodeYellow.SetBackgroundVolumeID(self.currentIntraopVolume.GetID())

    self.redSliceLogic.FitSliceToAll()
    self.yellowSliceLogic.FitSliceToAll()

    self.refreshViewNodeIDs(self.preopTargets, self.redSliceNode)
    self.refreshViewNodeIDs(self.outputTargets['Rigid'], self.yellowSliceNode)
    self.refreshViewNodeIDs(self.outputTargets['BSpline'], self.yellowSliceNode)

    if 'Affine' in self.outputTargets.keys():
      self.refreshViewNodeIDs(self.outputTargets['Affine'], self.yellowSliceNode)

    self.resetToRegularViewMode()

    # set Side By Side View to compare volumes
    self.layoutManager.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutSideBySideView)

    # Hide Labels
    self.compositeNodeRed.SetLabelOpacity(0)
    self.compositeNodeYellow.SetLabelOpacity(0)

    self.setAxialOrientation()

    self.tabBar.setTabEnabled(3,True)

    # switch to Evaluation Section
    self.tabWidget.setCurrentIndex(3)
    self.onBSplineResultClicked()

  def refreshViewNodeIDs(self, targets, sliceNode):
    # remove view node ID's from Red Slice view
    displayNode = targets.GetDisplayNode()
    displayNode.RemoveAllViewNodeIDs()
    displayNode.AddViewNodeID(sliceNode.GetID())

  def checkTabAfterImport(self):
    # change icon of tabBar if user is not in Data selection tab
    if not self.tabWidget.currentIndex == 0:
      self.tabBar.setTabIcon(0,self.newImageDataIcon)


class SliceTrackerLogic(ScriptedLoadableModuleLogic):

  INITIAL_REGISTRATION = 'InitialRegistration'
  NEEDLE_IMAGE_REGISTRATION = 'NeedleConfirmation'

  def __init__(self, parent=None):
    ScriptedLoadableModuleLogic.__init__(self, parent)
    self.inputMarkupNode = None
    self.clippingModelNode = None
    self.volumes = {}
    self.transforms = {}
    self.reRegistrationCount = 0

  def getRegistrationName(self):
    if self.reRegistrationCount == 0:
      return "COVER PROSTATE"
    else:
      return "GUIDANCE_FOR_NEEDLE_" + str(self.reRegistrationCount)

  def applyBiasCorrection(self, volume, label):

    progress = SliceTrackerWidget.makeProgressIndicator(2, 1)
    progress.labelText = '\nBias Correction'

    outputVolume = slicer.vtkMRMLScalarVolumeNode()
    outputVolume.SetName('volume-PREOP-N4')
    slicer.mrmlScene.AddNode(outputVolume)
    params = {'inputImageName': volume.GetID(),
              'maskImageName': label.GetID(),
              'outputImageName': outputVolume.GetID(),
              'numberOfIterations': '500,400,300'}

    self.cliNode = None
    self.cliNode = slicer.cli.run(slicer.modules.n4itkbiasfieldcorrection, self.cliNode, params,
                                  wait_for_completion=True)

    progress.setValue(2)
    progress.close()
    return outputVolume

  def createVolumeAndTransformNodes(self, registrationTypes, suffix):
    self.volumes = {}
    self.transforms = {}
    for regType in registrationTypes:
      name = regType + '-' + suffix
      isBSpline = regType=='BSpline'
      self.transforms[regType] = self.createTransformNode(name, isBSpline)
      self.volumes[regType] = self.createVolumeNode(name)

  def createTransformNode(self, suffix, isBSpline):
    node = slicer.vtkMRMLBSplineTransformNode() if isBSpline else slicer.vtkMRMLLinearTransformNode()
    node.SetName('transform-'+suffix)
    slicer.mrmlScene.AddNode(node)
    return node

  def createVolumeNode(self, suffix):
    volume = slicer.vtkMRMLScalarVolumeNode()
    volume.SetName('volume-' + suffix)
    slicer.mrmlScene.AddNode(volume)
    return volume

  def applyRegistration(self,fixedVolume,movingVolume,fixedLabel,movingLabel,targets):

    if fixedVolume and movingVolume and fixedLabel and movingLabel:
      self.fixedVolume = fixedVolume
      self.movingVolume = movingVolume
      self.fixedLabel = fixedLabel
      self.movingLabel = movingLabel

      progress = SliceTrackerWidget.makeProgressIndicator(4, 1)

      self.createVolumeAndTransformNodes(['Rigid', 'Affine', 'BSpline'], self.INITIAL_REGISTRATION)

      progress.labelText = '\nRigid registration'
      self.doRigidRegistration(movingBinaryVolume=self.movingLabel, initializeTransformMode="useCenterOfROIAlign")

      progress.labelText = '\nAffine registration'
      progress.setValue(2)
      self.doAffineRegistration()

      progress.labelText = '\nBSpline registration'
      progress.setValue(3)
      self.doBSplineRegistration(initialTransform=self.transforms['Affine'], useScaleVersor3D=False, useScaleSkewVersor3D=True,
                                 movingBinaryVolume=self.movingLabel, useAffine=False, samplingPercentage="0.002",
                                 maskInferiorCutOffFromCenter="1000", numberOfHistogramBins="50",
                                 numberOfMatchPoints="10", metricSamplingStrategy="Random", costMetric="MMI")

      outputTargets = self.transformTargets(['Rigid', 'Affine', 'BSpline'], targets, self.INITIAL_REGISTRATION)

      progress.labelText = '\nCompleted Registration'
      progress.setValue(4)
      progress.close()

      self.reRegistrationCount = 0

      return self.volumes, self.transforms, outputTargets

  def applyReRegistration(self, fixedVolume, movingVolume, fixedLabel, targets, lastRigidTfm):

    if fixedVolume and movingVolume and fixedLabel and lastRigidTfm:
      self.fixedVolume = fixedVolume
      self.movingVolume = movingVolume
      self.fixedLabel = fixedLabel

      progress = SliceTrackerWidget.makeProgressIndicator(4, 1)
      prefix = self.NEEDLE_IMAGE_REGISTRATION + str(self.reRegistrationCount)

      self.createVolumeAndTransformNodes(['Rigid', 'BSpline'], prefix)

      progress.labelText = '\nRigid registration'
      progress.setValue(2)

      self.doRigidRegistration(initialTransform=lastRigidTfm)

      self.dilateMask(fixedLabel)

      progress.labelText = '\nBSpline registration'
      progress.setValue(3)
      self.doBSplineRegistration(initialTransform=self.transforms['Rigid'], useScaleVersor3D=True,
                                 useScaleSkewVersor3D=True, useAffine=True)

      outputTargets = self.transformTargets(['Rigid', 'BSpline'], targets, prefix)

      progress.labelText = '\nCompleted Registration'
      progress.setValue(4)
      progress.close()
      self.reRegistrationCount += 1

      return self.volumes, self.transforms, outputTargets

  def doBSplineRegistration(self, initialTransform, useScaleVersor3D, useScaleSkewVersor3D, **kwargs):
    paramsBSpline = {'fixedVolume': self.fixedVolume,
                     'movingVolume': self.movingVolume,
                     'outputVolume': self.volumes['BSpline'].GetID(),
                     'bsplineTransform': self.transforms['BSpline'].GetID(),
                     'fixedBinaryVolume': self.fixedLabel,
                     'useRigid': False,
                     'useROIBSpline': True,
                     'useBSpline': True,
                     'useScaleVersor3D': useScaleVersor3D,
                     'useScaleSkewVersor3D': useScaleSkewVersor3D,
                     'splineGridSize': "3,3,3",
                     'numberOfIterations': "1500",
                     'maskProcessing': "ROI",
                     'outputVolumePixelType': "float",
                     'backgroundFillValue': "0",
                     'interpolationMode': "Linear",
                     'minimumStepLength': "0.005",
                     'translationScale': "1000",
                     'reproportionScale': "1",
                     'skewScale': "1",
                     'fixedVolumeTimeIndex': "0",
                     'movingVolumeTimeIndex': "0",
                     'medianFilterSize': "0,0,0",
                     'ROIAutoDilateSize': "0",
                     'relaxationFactor': "0.5",
                     'maximumStepLength': "0.2",
                     'failureExitCode': "-1",
                     'numberOfThreads': "-1",
                     'debugLevel': "0",
                     'costFunctionConvergenceFactor': "1.00E+09",
                     'projectedGradientTolerance': "1.00E-05",
                     'maxBSplineDisplacement': "0",
                     'maximumNumberOfEvaluations': "900",
                     'maximumNumberOfCorrections': "25",
                     'removeIntensityOutliers': "0",
                     'ROIAutoClosingSize': "9",
                     'maskProcessingMode': "ROI",
                     'initialTransform': initialTransform}
    for key, value in kwargs.iteritems():
      paramsBSpline[key] = value
    self.cliNode = None
    self.cliNode = slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsBSpline, wait_for_completion=True)

  def doAffineRegistration(self):
    paramsAffine = {'fixedVolume': self.fixedVolume,
                    'movingVolume': self.movingVolume,
                    'fixedBinaryVolume': self.fixedLabel,
                    'movingBinaryVolume': self.movingLabel,
                    'outputTransform': self.transforms['Affine'].GetID(),
                    'outputVolume': self.volumes['Affine'].GetID(),
                    'maskProcessingMode': "ROI",
                    'useAffine': True,
                    'initialTransform': self.transforms['Rigid']}
    self.cliNode = None
    self.cliNode = slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsAffine, wait_for_completion=True)

  def doRigidRegistration(self, **kwargs):
    paramsRigid = {'fixedVolume': self.fixedVolume,
                   'movingVolume': self.movingVolume,
                   'fixedBinaryVolume': self.fixedLabel,
                   'outputTransform': self.transforms['Rigid'].GetID(),
                   'outputVolume': self.volumes['Rigid'].GetID(),
                   'maskProcessingMode': "ROI",
                   'useRigid': True,
                   'useAffine': False,
                   'useBSpline': False,
                   'useScaleVersor3D': False,
                   'useScaleSkewVersor3D': False,
                   'useROIBSpline': False}
    for key, value in kwargs.iteritems():
      paramsRigid[key] = value
    self.cliNode = None
    self.cliNode = slicer.cli.run(slicer.modules.brainsfit, self.cliNode, paramsRigid, wait_for_completion=True)

  def transformTargets(self, registrations, targets, prefix):
    outputTargets = {}
    if targets:
      for registration in registrations:
        name = prefix + '-targets-' + registration
        outputTargets[registration] = self.cloneFiducialAndTransform(name, targets, self.transforms[registration])
    return outputTargets

  def cloneFiducialAndTransform(self, cloneName, originalTargets, transformNode):
    tfmLogic = slicer.modules.transforms.logic()
    clonedTargets = self.cloneFiducials(originalTargets, cloneName)
    clonedTargets.SetAndObserveTransformNodeID(transformNode.GetID())
    tfmLogic.hardenTransform(clonedTargets)
    # self.renameFiducials(clonedTargets)
    return clonedTargets

  def cloneFiducials(self, original, cloneName):
    mlogic = slicer.modules.markups.logic()
    nodeId = mlogic.AddNewFiducialNode(cloneName, slicer.mrmlScene)
    clone = slicer.mrmlScene.GetNodeByID(nodeId)
    for i in range(original.GetNumberOfFiducials()):
      pos = [0.0,0.0,0.0]
      original.GetNthFiducialPosition(i,pos)
      name = original.GetNthFiducialLabel(i)
      clone.AddFiducial(pos[0],pos[1],pos[2])
      clone.SetNthFiducialLabel(i,name)
    return clone

  def dilateMask(self,mask):

      import SimpleITK as sitk
      import sitkUtils

      logging.debug('mask ' + mask.GetName() +' is dilated')

      labelImage = sitk.ReadImage(sitkUtils.GetSlicerITKReadWriteAddress(mask.GetName()))

      grayscale_dilate_filter = sitk.GrayscaleDilateImageFilter()
      grayscale_dilate_filter.SetKernelRadius([12,12,0])
      grayscale_dilate_filter.SetKernelType(sitk.sitkBall)
      labelImage=grayscale_dilate_filter.Execute(labelImage)

      sitk.WriteImage(labelImage, sitkUtils.GetSlicerITKReadWriteAddress(mask.GetName()))
      logging.debug('dilate mask through')


  def renameFiducials(self,fiducialNode):
    # rename the targets to "[targetname]-REG"
    numberOfTargets = fiducialNode.GetNumberOfFiducials()
    logging.debug('number of targets : '+str(numberOfTargets))

    for index in range(numberOfTargets):
      oldname = fiducialNode.GetNthFiducialLabel(index)
      fiducialNode.SetNthFiducialLabel(index,str(oldname)+'-REG')
      logging.debug('changed name from '+oldname+' to '+str(oldname)+'-REG')

  def initializeListener(self,directory):
    numberOfFiles = len([item for item in os.listdir(directory)])
    self.lastFileCount = numberOfFiles
    self.directory = directory
    self.createCurrentFileList(directory)
    self.startTimer()

  def startTimer(self):
    currentFileCount = len(os.listdir(self.directory))
    if self.lastFileCount < currentFileCount:
     self.waitingForSeriesToBeCompleted()
    self.lastFileCount = currentFileCount
    qt.QTimer.singleShot(500, self.startTimer)

  def createCurrentFileList(self,directory):

    self.currentFileList = []
    for item in os.listdir(directory):
      self.currentFileList.append(item)

    if len(self.currentFileList) > 1:
      self.thereAreFilesInTheFolderFlag = 1
      self.importDICOMSeries()
    else:
      self.thereAreFilesInTheFolderFlag = 0

  def createLoadableFileListFromSelection(self,selectedSeriesList,directory):

    # this function creates a DICOM filelist for all files in intraop directory.
    # It compares the names of the studies in seriesList to the
    # DICOM tag of the DICOM filelist and creates a new list of list loadable
    # list, where it puts together all DICOM files of one series into one list

    db = slicer.dicomDatabase

    # create dcmFileList that lists all .dcm files in directory
    if os.path.exists(directory):
      dcmFileList = []
      for dcm in os.listdir(directory):
        if dcm != ".DS_Store":
          dcmFileList.append(os.path.join(directory, dcm))

      self.selectedFileList = []

      # write all selected files in selectedFileList
      for currentFile in dcmFileList:
       if db.fileValue(currentFile,DICOMTAGS.SERIES_DESCRIPTION) in selectedSeriesList:
         self.selectedFileList.append(currentFile)

      # create a list with lists of files of each series in them
      self.loadableList = []

      # add all found series to loadableList
      for series in selectedSeriesList:
        fileListOfSeries = []
        for currentFile in self.selectedFileList:
          if db.fileValue(currentFile,DICOMTAGS.SERIES_DESCRIPTION) == series:
            fileListOfSeries.append(currentFile)
        self.loadableList.append(fileListOfSeries)

  def loadSeriesIntoSlicer(self, selectedSeries, directory):

    self.createLoadableFileListFromSelection(selectedSeries, directory)

    for series in range(len(selectedSeries)):

      # get the filelist for the current series only
      files = self.loadableList[series]

      # create DICOMScalarVolumePlugin and load selectedSeries data from files into slicer
      scalarVolumePlugin = slicer.modules.dicomPlugins['DICOMScalarVolumePlugin']()

      try:
        loadables = scalarVolumePlugin.examine([files])
      except:
        logging.debug('There is nothing to load. You have to select series')

      name = loadables[0].name
      v = scalarVolumePlugin.load(loadables[0])
      v.SetName(name)
      slicer.mrmlScene.AddNode(v)

    # return the last series to continue with segmentation
    return v

  def importStudy(self, dicomDataDir):
    indexer = ctk.ctkDICOMIndexer()
    indexer.addDirectory(slicer.dicomDatabase, dicomDataDir)
    indexer.waitForImportFinished()

  def waitingForSeriesToBeCompleted(self):

    logging.debug('**  new data in intraop directory detected **')
    logging.debug('waiting 5 more seconds for the series to be completed')

    qt.QTimer.singleShot(5000,self.importDICOMSeries)

  def importDICOMSeries(self):

    self.newFileList = []
    self.seriesList = []
    self.selectableSeries = []
    self.acqusitionTimes = {}
    indexer = ctk.ctkDICOMIndexer()
    db = slicer.dicomDatabase

    if self.thereAreFilesInTheFolderFlag == 1:
      self.newFileList = self.currentFileList
      self.thereAreFilesInTheFolderFlag = 0
    else:
      # create a List NewFileList that contains only new files in the intraop directory
      for item in os.listdir(self.directory):
        if item not in self.currentFileList:
          if not item == ".DS_Store":
            self.newFileList.append(item)

    # import file in DICOM database
    for currentFile in self.newFileList:
      indexer.addFile(db,os.path.join(self.directory, currentFile),None)
      # logging.debug('file '+str(file)+' was added by Indexer')

      # add Series to seriesList
      if db.fileValue(os.path.join(self.directory, currentFile),DICOMTAGS.SERIES_DESCRIPTION) not in self.seriesList:
        importfile = os.path.join(self.directory, currentFile)
        self.seriesList.append(db.fileValue(importfile,DICOMTAGS.SERIES_DESCRIPTION))

        # get acquisition time and save in dictionary
        acqTime = db.fileValue(importfile,DICOMTAGS.ACQUISITION_TIME)[0:6]
        self.acqusitionTimes[str(db.fileValue(importfile,DICOMTAGS.SERIES_DESCRIPTION))] = str(acqTime)

    indexer.addDirectory(db,str(self.directory))
    indexer.waitForImportFinished()

    # pass items from seriesList to selectableSeries to keep them in the right order
    for series in self.seriesList:
      if series not in self.selectableSeries:
        self.selectableSeries.append(series)

    # sort list by acquisition time
    self.selectableSeries = self.sortSeriesByAcquisitionTime(self.selectableSeries)

    # TODO: update GUI from here is not very nice. Find a way to call logic and get the self.selectableSeries
    # as a return

    slicer.modules.SliceTrackerWidget.patientCheckAfterImport(self.directory, self.newFileList)
    slicer.modules.SliceTrackerWidget.checkTabAfterImport()

  def sortSeriesByAcquisitionTime(self,inputSeriesList):
    # this function sorts the self.acqusitionTimes
    # dictionary over its acquisiton times (values).
    # it returnes a sorted series list (keys) whereas
    # the 0th item is the earliest obtained series

    sortedList = sorted(self.acqusitionTimes, key=self.acqusitionTimes.get)
    return sortedList

  def removeEverythingInIntraopTestFolder(self):
    cmd = ('rm -rfv '+slicer.modules.SliceTrackerWidget.modulePath +'Resources/Testing/intraopDir/*')
    try:
      os.system(cmd)
    except:
      logging.debug('DEBUG: could not delete files in ' + self.modulePath+'Resources/Testing/intraopDir')

  def getNeedleTipAndTargetsPositions(self):

    # Get the fiducial lists
    fidNode1=slicer.mrmlScene.GetNodesByName('targets-BSPLINE').GetItemAsObject(0)
    fidNode2=slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)

    # get the needleTip_position
    self.needleTip_position = [0.0,0.0,0.0]
    fidNode2.GetNthFiducialPosition(0,self.needleTip_position)

    # get the target position(s)
    number_of_targets = fidNode1.GetNumberOfFiducials()
    self.target_positions = []

    for target in range(number_of_targets):
      target_position = [0.0,0.0,0.0]
      fidNode1.GetNthFiducialPosition(target,target_position)
      self.target_positions.append(target_position)

    logging.debug('needleTip_position = '+str(self.needleTip_position))
    logging.debug('target_positions are '+str(self.target_positions))

    return [self.needleTip_position,self.target_positions]

  def setNeedleTipPosition(self):

    if slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0) is None:

      # if needle tip is placed for the first time:

      # create Markups Node & display node to store needle tip position
      needleTipMarkupDisplayNode = slicer.vtkMRMLMarkupsDisplayNode()
      needleTipMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
      needleTipMarkupNode.SetName('needle-tip')
      slicer.mrmlScene.AddNode(needleTipMarkupDisplayNode)
      slicer.mrmlScene.AddNode(needleTipMarkupNode)
      needleTipMarkupNode.SetAndObserveDisplayNodeID(needleTipMarkupDisplayNode.GetID())

      # dont show needle tip in red Slice View
      needleNode = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)
      needleDisplayNode = needleNode.GetDisplayNode()
      needleDisplayNode.AddViewNodeID(slicer.modules.SliceTrackerWidget.yellowSliceNode.GetID())

      # update the target table when markup was set
      needleTipMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,
                                      slicer.modules.SliceTrackerWidget.updateTargetTable)

      # be sure to have the correct display node
      needleTipMarkupDisplayNode = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0).GetDisplayNode()

      # Set visual fiducial attributes
      needleTipMarkupDisplayNode.SetTextScale(1.6)
      needleTipMarkupDisplayNode.SetGlyphScale(2.0)
      needleTipMarkupDisplayNode.SetGlyphType(12)
      #TODO: set color is somehow not working here
      needleTipMarkupDisplayNode.SetColor(1,1,50)

    else:
      # remove fiducial
      needleNode = slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0)
      needleNode.RemoveAllMarkups()

      # clear target table
      slicer.modules.SliceTrackerWidget.clearTargetTable()

    # set active node ID and start place mode
    mlogic = slicer.modules.markups.logic()
    mlogic.SetActiveListID(slicer.mrmlScene.GetNodesByName('needle-tip').GetItemAsObject(0))
    slicer.modules.markups.logic().StartPlaceMode(0)

  def measureDistance(self,target_position,needleTip_position):

    # calculate 2D distance
    distance_2D_x = abs(target_position[0]-needleTip_position[0])
    distance_2D_y = abs(target_position[1]-needleTip_position[1])
    distance_2D_z = abs(target_position[2]-needleTip_position[2])

    # calculate 3D distance
    distance_3D = self.get3dDistance(needleTip_position, target_position)

    return [distance_2D_x,distance_2D_y,distance_2D_z,distance_3D]

  def get3dDistance(self, needleTip_position, target_position):
    rulerNode = slicer.vtkMRMLAnnotationRulerNode()
    rulerNode.SetPosition1(target_position)
    rulerNode.SetPosition2(needleTip_position)
    distance_3D = rulerNode.GetDistanceMeasurement()
    return distance_3D

  def setupColorTable(self):

    # setup the PCampReview color table

    self.colorFile = os.path.join(slicer.modules.SliceTrackerWidget.modulePath, 'Resources/Colors/PCampReviewColors.csv')
    self.PCampReviewColorNode = slicer.vtkMRMLColorTableNode()
    colorNode = self.PCampReviewColorNode
    colorNode.SetName('PCampReview')
    slicer.mrmlScene.AddNode(colorNode)
    colorNode.SetTypeToUser()
    with open(self.colorFile) as f:
      n = sum(1 for line in f)
    colorNode.SetNumberOfColors(n-1)
    import csv
    self.structureNames = []
    with open(self.colorFile, 'rb') as csvfile:
      reader = csv.DictReader(csvfile, delimiter=',')
      for index,row in enumerate(reader):
        colorNode.SetColor(index,row['Label'],float(row['R'])/255,
                float(row['G'])/255,float(row['B'])/255,float(row['A']))
        self.structureNames.append(row['Label'])

  def takeScreenshot(self,name,description,layout=-1):
    # show the message even if not taking a screen shot
    self.delayDisplay(description)

    if self.enableScreenshots == 0:
      return

    lm = slicer.app.layoutManager()
    # switch on the type to get the requested window
    widget = 0
    if layout == slicer.qMRMLScreenShotDialog.FullLayout:
      # full layout
      widget = lm.viewport()
    elif layout == slicer.qMRMLScreenShotDialog.ThreeD:
      # just the 3D window
      widget = lm.threeDWidget(0).threeDView()
    elif layout == slicer.qMRMLScreenShotDialog.Red:
      # red slice window
      widget = lm.sliceWidget("Red")
    elif layout == slicer.qMRMLScreenShotDialog.Yellow:
      # yellow slice window
      widget = lm.sliceWidget("Yellow")
    elif layout == slicer.qMRMLScreenShotDialog.Green:
      # green slice window
      widget = lm.sliceWidget("Green")
    else:
      # default to using the full window
      widget = slicer.util.mainWindow()
      # reset the layout so that the node is set correctly
      layout = slicer.qMRMLScreenShotDialog.FullLayout

    # grab and convert to vtk image data
    qpixMap = qt.QPixmap().grabWidget(widget)
    qimage = qpixMap.toImage()
    imageData = vtk.vtkImageData()
    slicer.qMRMLUtils().qImageToVtkImageData(qimage,imageData)

    annotationLogic = slicer.modules.annotations.logic()
    annotationLogic.CreateSnapShot(name, description, layout, self.screenshotScaleFactor, imageData)

  def run(self):
    return True

  def runQuickSegmentationMode(self):
    self.setVolumeClipUserMode()
    self.placeFiducials()

  def setVolumeClipUserMode(self):
    lm = slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutFourUpView)

    for widgetName in ['Red', 'Green', 'Yellow']:
      slice = lm.sliceWidget(widgetName)
      sliceLogic = slice.sliceLogic()
      sliceLogic.FitSliceToAll()

    # set the mouse mode into Markups fiducial placement
    placeModePersistence = 1
    slicer.modules.markups.logic().StartPlaceMode(placeModePersistence)

  def updateModel(self,observer,caller):
    import VolumeClipWithModel
    clipLogic = VolumeClipWithModel.VolumeClipWithModelLogic()
    clipLogic.updateModelFromMarkup(self.inputMarkupNode, self.clippingModelNode)

  def deleteClippingData(self):
    slicer.mrmlScene.RemoveNode(self.clippingModelNode)
    logging.debug('deleted ModelNode')
    slicer.mrmlScene.RemoveNode(self.inputMarkupNode)
    logging.debug('deleted inputMarkupNode')

  def placeFiducials(self):

    self.clippingModelNode = slicer.vtkMRMLModelNode()
    self.clippingModelNode.SetName('clipModelNode')
    slicer.mrmlScene.AddNode(self.clippingModelNode)

    self.createClippingModelDisplayNode()
    self.createMarkupAndDisplayNodeForFiducials()
    self.inputMarkupNode.AddObserver(vtk.vtkCommand.ModifiedEvent,self.updateModel)

  def createMarkupAndDisplayNodeForFiducials(self):
    displayNode = slicer.vtkMRMLMarkupsDisplayNode()
    slicer.mrmlScene.AddNode(displayNode)
    self.inputMarkupNode = slicer.vtkMRMLMarkupsFiducialNode()
    self.inputMarkupNode.SetName('inputMarkupNode')
    slicer.mrmlScene.AddNode(self.inputMarkupNode)
    self.inputMarkupNode.SetAndObserveDisplayNodeID(displayNode.GetID())
    self.styleDisplayNode(displayNode)

  def styleDisplayNode(self, displayNode):
    displayNode.SetTextScale(0)
    displayNode.SetGlyphScale(2.0)
    displayNode.SetColor(0, 0, 0)

  def createClippingModelDisplayNode(self):
    clippingModelDisplayNode = slicer.vtkMRMLModelDisplayNode()
    clippingModelDisplayNode.SetSliceIntersectionThickness(3)
    clippingModelDisplayNode.SetColor((20, 180, 250))
    slicer.mrmlScene.AddNode(clippingModelDisplayNode)
    self.clippingModelNode.SetAndObserveDisplayNodeID(clippingModelDisplayNode.GetID())

  def labelMapFromClippingModel(self,inputVolume):
    """
    PARAMETER FOR MODELTOLABELMAP CLI MODULE:
    Parameter (0/0): sampleDistance
    Parameter (0/1): labelValue
    Parameter (1/0): InputVolume
    Parameter (1/1): surface
    Parameter (1/2): OutputVolume
    """
    # initialize Label Map
    outputLabelMap = slicer.vtkMRMLLabelMapVolumeNode()
    name = (slicer.modules.SliceTrackerWidget.referenceVolumeSelector.currentNode().GetName()+ '-label')
    outputLabelMap.SetName(name)
    slicer.mrmlScene.AddNode(outputLabelMap)

    if outputLabelMap:
      'outoutLabelMap is here!'

    # define params
    params = {'sampleDistance': 0.1, 'labelValue': 5, 'InputVolume' : inputVolume.GetID(),
              'surface' : self.clippingModelNode.GetID(), 'OutputVolume' : outputLabelMap.GetID()}

    logging.debug(params)
    # run ModelToLabelMap-CLI Module
    cliNode = slicer.cli.run(slicer.modules.modeltolabelmap, None, params, wait_for_completion=True)

    # use label contours
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").SetUseLabelOutline(True)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").SetUseLabelOutline(True)

    # rotate volume to plane
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeRed").RotateToVolumePlane(outputLabelMap)
    slicer.mrmlScene.GetNodeByID("vtkMRMLSliceNodeYellow").RotateToVolumePlane(outputLabelMap)

    # set Layout to redSliceViewOnly
    lm = slicer.app.layoutManager()
    lm.setLayout(slicer.vtkMRMLLayoutNode.SlicerLayoutOneUpRedSliceView)

    # fit Slice View to FOV
    red = lm.sliceWidget('Red')
    redLogic = red.sliceLogic()
    redLogic.FitSliceToAll()

    # set Label Opacity Back
    redWidget = lm.sliceWidget('Red')
    compositeNodeRed = redWidget.mrmlSliceCompositeNode()
    # compositeNodeRed.SetLabelVolumeID(outputLabelMap.GetID())
    compositeNodeRed.SetLabelOpacity(1)
    return outputLabelMap

  def BRAINSResample(self,inputVolume,referenceVolume,outputVolume,warpTransform):
    """
    Parameter (0/0): inputVolume
    Parameter (0/1): referenceVolume
    Parameter (1/0): outputVolume
    Parameter (1/1): pixelType
    Parameter (2/0): deformationVolume
    Parameter (2/1): warpTransform
    Parameter (2/2): interpolationMode
    Parameter (2/3): inverseTransform
    Parameter (2/4): defaultValue
    Parameter (3/0): gridSpacing
    Parameter (4/0): numberOfThreads
    """

    params = {'inputVolume': inputVolume, 'referenceVolume': referenceVolume, 'outputVolume' : outputVolume,
              'warpTransform' : warpTransform,'interpolationMode' : 'NearestNeighbor'}

    logging.debug('about to run BRAINSResample CLI with those params: ')
    logging.debug(params)
    slicer.cli.run(slicer.modules.brainsresample, None, params, wait_for_completion=True)
    logging.debug('resample labelmap through')
    slicer.mrmlScene.AddNode(outputVolume)


class SliceTrackerTest(ScriptedLoadableModuleTest):
  """
  This is the test case for your scripted module.
  Uses ScriptedLoadableModuleTest base class, available at:
  https://github.com/Slicer/Slicer/blob/master/Base/Python/slicer/ScriptedLoadableModule.py
  """

  def setUp(self):
    """ Do whatever is needed to reset the state - typically a scene clear will be enough.
    """
    slicer.mrmlScene.Clear(0)


  def runTest(self):
    """Run as few or as many tests as needed here.
    """
    self.setUp()
    self.test_SliceTracker1()

  def test_SliceTracker1(self):
    """ Ideally you should have several levels of tests.  At the lowest level
    tests should exercise the functionality of the logic with different inputs
    (both valid and invalid).  At higher levels your tests should emulate the
    way the user would interact with your code and confirm that it still works
    the way you intended.
    One of the most important features of the tests is that it should alert other
    developers when their changes will have an impact on the behavior of your
    module.  For example, if a developer removes a feature that you depend on,
    your test should break so they know that the feature is needed.
    """
    logging.debug(' ___ performing selfTest ___ ')
