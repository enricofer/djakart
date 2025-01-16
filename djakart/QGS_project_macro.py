
import sys
import re
from PyQt5.QtCore import Qt
from qgis.core import QgsProject, QgsRectangle, QgsFeatureRequest
from qgis.utils import iface
from PyQt5.QtWidgets import (QDialog, QWidget, QDialogButtonBox, QPushButton, QLabel, QLineEdit, QGridLayout, QMessageBox)

ZTO_LAYER_NAME = 'b0501011_ZTO'

def saveProject():
    pass

def closeProject():
    pass

def openProject():

    class LoginForm(QDialog):
        def __init__(self, u, p):
            super().__init__()
            self.setWindowTitle('Inserimento credeziali')
            self.resize(500, 120)

            layout = QGridLayout()

            label_name = QLabel('Username')
            self.lineEdit_username = QLineEdit()
            if not u:
                self.lineEdit_username.setPlaceholderText('Inserire il proprio username')
            else:
                self.lineEdit_username.setText(u)
            layout.addWidget(label_name, 0, 0)
            layout.addWidget(self.lineEdit_username, 0, 1)

            label_password = QLabel('Password')
            self.lineEdit_password = QLineEdit()
            self.lineEdit_password.setEchoMode(QLineEdit.Password)
            if not p:
                self.lineEdit_password.setPlaceholderText('Inserire la propria password')
            else:
                self.lineEdit_password.setText(p)
            layout.addWidget(label_password, 1, 0)
            layout.addWidget(self.lineEdit_password, 1, 1)

        # OK and Cancel buttons
            buttons = QDialogButtonBox(
                QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                Qt.Horizontal, self)
            buttons.accepted.connect(self.accept)
            buttons.rejected.connect(self.reject)
            layout.addWidget(buttons)
            layout.setRowMinimumHeight(2, 75)

            self.setLayout(layout)

        def check_password(self):
            self.user = self.lineEdit_username.text()
            self.password = self.lineEdit_password.text()
            return self.lineEdit_username.text(), self.lineEdit_password.text()

        @staticmethod
        def getCredentials(user=None, password=None, parent = None):
            dialog = LoginForm(user,password)
            result = dialog.exec_()
            user, password = dialog.check_password()
            return (user, password, result == QDialog.Accepted)
            
    if not hasattr(iface, 'session_password'):
        u,p,r = LoginForm.getCredentials()
        iface.session_username = u
        iface.session_password = p
    else:
        r = QDialog.Accepted
        u = iface.session_username
        p = iface.session_password
        u,p,r = LoginForm.getCredentials(u,p)
    
    #print(u,p,r)

    for layerName,layer in QgsProject.instance().mapLayers().items():
        print('"%s",' % layerName)
        if layer.name() == ZTO_LAYER_NAME:
            layer.attributeValueChanged.connect(aggiornaCampiSpecifiche)
            print ("COLLEGATO")
            
        if r == QDialog.Accepted and u and p and layer.providerType() == 'postgres':
            ls = layer.source()
            ls = re.sub("(ser='.*?('))", "ser='%s'" % u, ls)
            ls = re.sub("(assword='.*?('))", "assword='%s'" % p, ls)
            layer.setDataSource(ls,layer.name(),'postgres')

        if layer.name().upper().startswith("PERIMETRO") or layer.name().upper() == 'PUA':
            #f = layer.getFeature(0)
            #print ("Extensions:",f.geometry().boundingBox())
            #iface.mapCanvas().zoomToFeatureExtent(list(layer.getFeatures())[0].geometry().boundingBox())
            flist = [f.id() for f in layer.getFeatures()]
            if flist:
                iface.mapCanvas().zoomToFeatureIds(layer,flist)
            else:
                iface.mapCanvas().zoomToFullExtent()
        
def closeProject():
    pass

def aggiornaCampiSpecifiche(FID,attr_idx,value):
    zto_layer = None
    for layerName,layer in QgsProject.instance().mapLayers().items():
        if layer.name() == ZTO_LAYER_NAME and layer.isEditable():
            zto_layer = layer
            break
    
    if not zto_layer:
        print ("Layer zto non trovato")
        return
    
    campo_in_aggiornamento = zto_layer.fields().at(attr_idx).name()
    
    if not campo_in_aggiornamento in ('UMS','Sub_3','Sub_4','ZTO','sigla'):
        return

    print (zto_layer)

    pk_ums = {
        '00': 0,
        '11': 0,
        '12': 0,
        '13': 0,
        '14': 0,
        '15': 0,
        '16': 0,
    }

    decode_ABCDE = {
        'A': '11',
        'B': '12',
        'C': '13',
        'D': '14',
        'E': '15',
    }

    decode_F2 = {
        'servizi amministrativi': '41',
        'servizi per il tempo libero': '25',
        'servizi religiosi': '12',
        'servizi sanitari': '35',
        'servizi socio-assistenziali': '28',
        'servizi socio-culturali': '19',
        'servizi tecnologici': '71',
    }

    decode_F2_reverse = {
        'servizi amministrativi': 'a',
        'servizi per il tempo libero': 'b',
        'servizi religiosi': 'c',
        'servizi sanitari': 'd',
        'servizi socio-assistenziali': 'e',
        'servizi socio-culturali': 'f',
        'servizi tecnologici': 'g',
    }

    decode_F5 = {
        'a': '50',
        'b': '05',
        'c': '19',
        'd': '35',
        'e': '28',
        'f': '99',
        'g': '56',
        'h': '60',
        'i': '80',
        'j': '61',
        'k': '00',
    }

    decode_F6 = {
        'a': '86',
        'b': '92',
        'c': '94',
        'd': '02',
    }

    id_set = set()

    #zto_layer.startEditing()
    
    feat = next(zto_layer.getFeatures(QgsFeatureRequest(FID)))
    
    feat["ZTO"] = str(feat["ZTO"]).upper()
    feat["sigla"] = str(feat["sigla"]).lower()

    if feat["ZTO"][0] in ('A', 'B', 'C', 'D', 'E'):
        feat["Sub_1"] = decode_ABCDE[feat["ZTO"][0]]
        feat["Sub_2"] = '0' + feat["ZTO"][1]
    elif feat["ZTO"].startswith('F'):
        feat["Sub_1"] = '16'
        if feat["ZTO"] == 'F1':
            feat["Sub_2"] = '04'
        elif feat["ZTO"] == 'F2':
            feat["Sub_2"] = decode_F2[feat["tipologia"]]
            feat["sigla"] = decode_F2_reverse[feat["tipologia"]]
        elif feat["ZTO"] == 'F3':
            feat["Sub_2"] = '83'
        elif feat["ZTO"] == 'F4':
            feat["Sub_2"] = '95'
        elif feat["ZTO"] == 'F5':
            feat["Sub_2"] = decode_F5[feat["sigla"]]
        elif feat["ZTO"] == 'F6':
            feat["Sub_2"] = decode_F6[feat["sigla"]]
            if feat["sigla"] == 'd':
                feat["Sub_1"] = '00'
    else:
        feat["Sub_1"] = '00'
        feat["Sub_2"] = '00'
        
    #feat["UMS"] = str(pk_ums[feat["Sub_1"]]).rjust(4, '0')
    #pk_ums[feat["Sub_1"]] += 1

    try:
        calc_ID_Zona = str(feat["cod_ISTAT"]) + str(feat["Sub_1"]) + str(feat["Sub_2"]) + str(feat["Sub_3"]) + str(feat["Sub_4"]) + str(feat["UMS"])
        print ("aggiornato", calc_ID_Zona)
    except:
        print(feat["ZTO"], feat["sigla"], type(feat["cod_ISTAT"]),type(feat["Sub_1"]),type(feat["Sub_2"]),type(feat["Sub_3"]),type(feat["Sub_4"]),type(feat["UMS"]))


    if feat["Sub_1"] != '00' and feat["ID_Zona"] in id_set:
        print ("ID NON univoco:", feat["ID_Zona"])
    id_set.add(feat["ID_Zona"])

    #if calc_ID_Zona != feat["ID_Zona"]:
    feat["ID_Zona"] = calc_ID_Zona
    res = zto_layer.updateFeature(feat)
    print ("cambiato", calc_ID_Zona, res)
            
    #zto_layer.commitChanges()

    