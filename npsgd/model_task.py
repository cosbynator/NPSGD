import os
import sys
import uuid
import logging
import subprocess
from email_manager import Email
import shutil

from config import config
from model_manager import ModelMount

class LatexError(RuntimeError): pass
class ModelTask(object):
    __metaclass__ = ModelMount
    abstractModel = "ModelTask"

    #Every model short implement a subset of these
    short_name  = "unspecified_name"
    subtitle    = "Unspecified Subtitle"
    attachments = []

    def __init__(self, emailAddress, taskId, modelParameters={}, failureCount=0):
        self.emailAddress      = emailAddress
        self.taskId            = taskId
        self.failureCount      = failureCount
        self.modelParameters   = []
        self.workingDirectory  = "/var/tmp/npsgd/%s" % str(uuid.uuid4())

        for k,v in modelParameters.iteritems():
            param = self.parameterType(k).fromDict(v)
            setattr(self, param.name, param)
            self.modelParameters.append(param)

    def createWorkingDirectory(self):
        try:
            os.mkdir(self.workingDirectory)
        except OSError, e:
            logging.warning(e)

    def parameterType(self, parameterName):
        for pClass in self.__class__.parameters:
            if parameterName == pClass.name:
                return pClass

        return None

    @classmethod
    def fromDict(cls, dictionary):
        emailAddress = dictionary["emailAddress"]
        taskId       = dictionary["taskId"]
        failureCount = dictionary["failureCount"]

        return cls(emailAddress, taskId, failureCount=failureCount,
                modelParameters=dictionary["modelParameters"])

    def asDict(self):
        return {
            "emailAddress" :   self.emailAddress,
            "taskId":          self.taskId, 
            "failureCount":    self.failureCount,
            "modelName":       self.__class__.short_name,
            "modelParameters": dict((p.name, p.asDict()) for p in self.modelParameters)
        }

    def latexBody(self):
        return "This is a test for %s" % self.emailAddress

    def latexParameterTable(self):
        paramRows = "\\\\\n".join(p.asLatexRow() for p in self.modelParameters)
        return """
        \\begin{centering}
        \\begin{tabular*}{6in}{@{\\extracolsep{\\fill}} c c c}
        \\textbf{Name} & \\textbf{Description} & \\textbf{Value} \\\\
        \\hline
        %s
        \\end{tabular*}
        \\end{centering}""" % paramRows

    def textParameterTable(self):
        return "Model:%s\nName, Description, Value, Units\n%s" % (self.__class__.short_name, "\n".join(p.asTextRow() for p in self.modelParameters))

    def emailBody(self):
        return "Model run results from NPSG"

    def emailTitle(self):
        return "Model run results from NPSG"

    def getAttachments(self):
        pdf = self.generatePDF()

        attach = [('results.pdf', pdf)]
        for attachment in self.__class__.attachments:
            with open(os.path.join(self.workingDirectory, attachment)) as f:
                attach.append((attachment, f.read()))

        return attach

    def generatePDF(self):
        latex = config.latexResultTemplate.generate(model_results=self.latexBody())
        logging.info(latex)

        texPath = os.path.join(self.workingDirectory, "test_task.tex")
        pdfOutputPath = os.path.join(self.workingDirectory, "test_task.pdf")

        with open(texPath, 'w') as f:
            f.write(latex)

        logging.info("Calling PDFLatex to generate pdf output")
        retCode = subprocess.call([config.pdfLatexPath, "-halt-on-error", texPath], cwd=self.workingDirectory)
        logging.info("PDFLatex terminated with error code %d", retCode)

        if retCode != 0:
            raise LatexError("Bad exit code from latex")

        with open(pdfOutputPath, 'rb') as f:
            pdf = f.read()

        return pdf


    def failureEmail(self):
        return Email(self.emailAddress, 
                config.failureEmailSubject,
                config.failureEmailTemplate.generate())

    def resultsEmail(self, attachments):
        return Email(self.emailAddress,
                config.resultsEmailSubject,
                config.resultsEmailBodyTemplate.generate(),
                attachments)

    def runModel(self):
        logging.warning("Called default run model - this should be overridden")

    def run(self):
        """Runs the model with parameters, the model email object unsent."""

        logging.info("Running default task for '%s'", self.emailAddress)
        self.createWorkingDirectory()
        try:
            self.runModel()
            return self.resultsEmail(self.getAttachments())
        finally:
            shutil.rmtree(self.workingDirectory)