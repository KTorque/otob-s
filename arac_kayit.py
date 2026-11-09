#!/usr/bin/env python3
"""
KM12 araç konumu kaydedici (GitHub Actions'ta çalışır).

İBB Açık Veri'nin araç servisinden her dakika hattaki otobüslerin kapı no ve GPS
konumunu alır, Google E-Tablo'daki Apps Script web uygulamasına (doPost) gönderir.
Satırlar e-tablonun "Araçlar" sekmesine yazılır. Bu iş Google'da değil burada
yapılır, çünkü İBB'nin araç servisi Google'ın sunucularından gelen istekleri kabul etmiyor.

Ortam değişkenleri (GitHub'da "secrets" olarak girilir):
  WEB_APP_URL     Apps Script web uygulaması adresi (.../exec)
  GIZLI_ANAHTAR   Apps Script kurulum günlüğündeki "gizli anahtar"
WEB_APP_URL yoksa satırlar gönderilmez, ekrana yazılır (deneme için).

Kullanım:
  python3 arac_kayit.py            # 07:00-09:30 arası her dakika, sonra çıkar
  python3 arac_kayit.py --deneme   # saat aralığına bakmadan tek bir kayıt al
"""

import html
import json
import math
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HAT = "KM12"
DURAK = "207762"
BASLANGIC = "07:00"  # İstanbul saati
BITIS = "09:30"

ISTANBUL = timezone(timedelta(hours=3))  # Türkiye 2016'dan beri sabit UTC+3
IBB_ARAC = "https://api.ibb.gov.tr/iett/FiloDurum/SeferGerceklesme.asmx"
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"

# KM12'nin iki yöndeki durakları (İBB açık veri, DurakDetay_GYY, 2 Kasım 2026)
# yön | sıra | kod | ad | enlem | boylam
DURAK_LISTESI = """
D|1|402061|KARTAL METRO|40.906602|29.208159
D|2|289342|D-100 GÜNEY YANYOL|40.904021|29.213884
D|3|206332|SELÇUK ERAYDIN ANADOLU İMAM HATİP LİSESİ|40.900559|29.219192
D|4|208312|KERESTECİLER|40.897674|29.223718
D|5|212842|VERGİ DAİRESİ|40.894684|29.228240
D|6|260131|SAFAŞ|40.892239|29.232077
D|7|227814|PENDİK KÖPRÜSÜ|40.887916|29.238651
D|8|261261|MEHMET ALİ TUNGA CAMİİ|40.886499|29.241000
D|9|212571|TAVŞANTEPE METRO|40.881910|29.247704
D|10|212581|KARADENİZ CADDESİ|40.880551|29.252059
D|11|225781|KAYNARCA|40.876695|29.262717
D|12|225801|TERSANE KÖPRÜSÜ-1|40.867608|29.271184
D|13|288861|TERSANE KÖPRÜSÜ-2|40.865889|29.273086
D|14|225812|GÜZELYALI KÖPRÜSÜ|40.859711|29.281152
D|15|262202|GÜLİZAR ZEKİ OBDAN ANADOLU LİSESİ|40.857608|29.286752
D|16|225832|ESENYALI SAPAĞI|40.854650|29.291883
D|17|260672|AYDINTEPE İSTASYON|40.852658|29.294139
D|18|225844|İÇMELER KÖPRÜSÜ|40.848623|29.296457
D|19|207742|TERSANELER|40.847753|29.295147
D|20|207731|ŞİFALI SULAR|40.845077|29.297830
D|21|207721|TUZLA BELEDİYESİ|40.843065|29.300486
D|22|208961|GÜLİSTAN|40.841498|29.304335
D|23|207711|EVLİYA ÇELEBİ CAMİİ|40.840889|29.306096
D|24|209372|YENİEVLER CAMİİ|40.838129|29.310302
D|25|208321|ERTUĞ SİTESİ|40.836397|29.312578
D|26|225822|HAT BOYU|40.833475|29.316013
D|27|207791|HİLMİ SONAY İLKOKULU|40.830286|29.319166
D|28|207781|TUZLA İSTASYONU|40.829294|29.321698
D|29|207762|HACIOĞLU SOKAK|40.827854|29.324550
D|30|211792|ALYAZMA SOKAK|40.825596|29.325516
D|31|289242|SAHİL GÜVENLİK İKMAL MERKEZİ KOMUTANLIĞI|40.821870|29.325151
D|32|225872|TUZLA MARİNA|40.822050|29.321015
D|33|225892|MARMADOS SİTESİ|40.819284|29.314610
D|34|207751|ŞEHİTLER CADDESİ|40.815989|29.312908
D|35|225902|SAHİL PARK|40.814498|29.307311
D|36|225922|TUZLA|40.815386|29.303550
D|37|206372|YAKAMOZ|40.816399|29.300707
D|38|225932|İTÜ DENİZCİLİK FAKÜLTESİ|40.816634|29.295047
D|39|207561|PİRİ REİS ÜNİVERSİTESİ|40.816586|29.289600
D|40|225942|KEREM SOKAK|40.817170|29.286851
D|41|225952|CENGAVER SOKAK|40.818025|29.283364
D|42|225962|ÇALI SOKAK|40.818224|29.279914
D|43|225972|MERCAN YUVASI|40.818303|29.276349
D|44|225911|ÖĞÜT SOKAK|40.816660|29.271964
D|45|225981|DENİZ HARP OKULU|40.814013|29.266183
G|1|225981|DENİZ HARP OKULU|40.814013|29.266183
G|2|225912|ÖĞÜT SOKAK|40.816804|29.272453
G|3|225971|MERCAN YUVASI|40.818102|29.276203
G|4|225961|ÇALI SOKAK|40.818051|29.280073
G|5|225951|CENGAVER SOKAK|40.817806|29.284138
G|6|225941|KEREM SOKAK|40.817048|29.286853
G|7|207562|PİRİ REİS ÜNİVERSİTESİ|40.816383|29.290239
G|8|225931|İTÜ DENİZCİLİK FAKÜLTESİ|40.816328|29.294434
G|9|206371|YAKAMOZ|40.816213|29.300636
G|10|225921|TUZLA|40.815109|29.303752
G|11|225901|SAHİL PARK|40.814192|29.307370
G|12|207752|ŞEHİTLER CADDESİ|40.815811|29.312929
G|13|225891|MARMADOS SİTESİ|40.819282|29.314756
G|14|225871|TUZLA MARİNA|40.820805|29.319347
G|15|289241|SAHİL GÜVENLİK İKMAL MERKEZİ KOMUTANLIĞI|40.821710|29.325234
G|16|211791|ALYAZMA SOKAK|40.825913|29.325539
G|17|207761|HACIOĞLU SOKAK|40.827827|29.324785
G|18|207782|TUZLA İSTASYONU|40.829371|29.321894
G|19|207792|HİLMİ SONAY İLKOKULU|40.830200|29.319779
G|20|225821|HAT BOYU|40.833491|29.316336
G|21|208322|ERTUĞ SİTESİ|40.836663|29.312487
G|22|209371|YENİEVLER CAMİİ|40.838233|29.310432
G|23|207712|EVLİYA ÇELEBİ CAMİİ|40.840890|29.306751
G|24|208962|GÜLİSTAN|40.841764|29.304147
G|25|207722|TUZLA BELEDİYESİ|40.844275|29.299365
G|26|207732|ŞİFALI SULAR|40.844492|29.295605
G|27|207741|TERSANELER|40.845975|29.294533
G|28|225842|İÇMELER KÖPRÜSÜ|40.849884|29.298022
G|29|260671|AYDINTEPE İSTASYON|40.852792|29.294822
G|30|225831|ESENYALI SAPAĞI|40.855126|29.292312
G|31|262201|GÜLİZAR ZEKİ OBDAN ANADOLU LİSESİ|40.856789|29.289780
G|32|225811|GÜZELYALI KÖPRÜSÜ|40.859887|29.281936
G|33|288862|TERSANE KÖPRÜSÜ-2|40.866189|29.273552
G|34|225802|TERSANE KÖPRÜSÜ-1|40.868170|29.271353
G|35|225782|KAYNARCA|40.878980|29.260434
G|36|212572|TAVŞANTEPE METRO|40.882292|29.248832
G|37|261262|MEHMET ALİ TUNGA CAMİ|40.886918|29.240759
G|38|227813|PENDİK KÖPRÜSÜ|40.888700|29.238214
G|39|260132|SAFAŞ|40.892558|29.232393
G|40|212841|VERGİ DAİRESİ|40.895948|29.227312
G|41|208311|KERESTECİLER|40.897688|29.224635
G|42|206331|SELÇUK ERAYDIN ANADOLU İMAM HATİP LİSESİ|40.900894|29.219731
G|43|225761|KARTAL KÖPRÜSÜ|40.905834|29.212114
G|44|211021|KARTAL KÖPRÜ ÇIKIŞI|40.905266|29.209843
G|45|402061|KARTAL METRO|40.906602|29.208159
"""

# (yön, kod) -> durak; ilk ve son durak iki yönde de aynı kodla geçer
DURAKLAR = {}
for _satir in DURAK_LISTESI.strip().splitlines():
    _yon, _sira, _kod, _ad, _enlem, _boylam = _satir.split("|")
    DURAKLAR[(_yon, _kod)] = {"sira": int(_sira), "ad": _ad, "enlem": float(_enlem), "boylam": float(_boylam)}


def durak_bul(kod, guzergah_kodu):
    """Aracın güzergâh kodundaki yöne (KM12_D_D0 -> D) göre durağı bulur."""
    m = re.search(r"_([DG])_", guzergah_kodu or "")
    for yon in ([m.group(1)] if m else []) + ["D", "G"]:
        if (yon, kod) in DURAKLAR:
            return DURAKLAR[(yon, kod)]
    return {}

SOAP_GOVDE = ('<?xml version="1.0" encoding="utf-8"?>'
              '<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
              '<GetHatOtoKonum_json xmlns="http://tempuri.org/"><HatKodu>{hat}</HatKodu>'
              '</GetHatOtoKonum_json></soap:Body></soap:Envelope>')


def simdi():
    return datetime.now(ISTANBUL)


def istek(adres, veri=None, basliklar=None, deneme=3):
    basliklar = dict(basliklar or {})
    basliklar.setdefault("User-Agent", USER_AGENT)
    son_hata = None
    for i in range(deneme):
        try:
            req = urllib.request.Request(adres, data=veri, headers=basliklar)
            with urllib.request.urlopen(req, timeout=25) as yanit:
                return yanit.read().decode("utf-8", errors="replace")
        except Exception as e:
            son_hata = e
            if i < deneme - 1:
                time.sleep(3 * (i + 1))
    raise RuntimeError("%s alınamadı: %s" % (adres.split("?")[0], son_hata))


def mesafe_m(enlem1, boylam1, enlem2, boylam2):
    if None in (enlem1, boylam1, enlem2, boylam2):
        return ""
    p1, p2 = math.radians(enlem1), math.radians(enlem2)
    dp = p2 - p1
    dl = math.radians(boylam2 - boylam1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(a)))


def sayi(deger):
    try:
        return float(deger)
    except (TypeError, ValueError):
        return None


def araclari_getir():
    ham = istek(IBB_ARAC, veri=SOAP_GOVDE.format(hat=html.escape(HAT)).encode("utf-8"), basliklar={
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": '"http://tempuri.org/GetHatOtoKonum_json"',
    })
    m = re.search(r"<GetHatOtoKonum_jsonResult>(.*?)</GetHatOtoKonum_jsonResult>", ham, re.S)
    if not m:
        if re.search(r"<GetHatOtoKonum_jsonResult\s*/>", ham):
            return []
        raise RuntimeError("beklenmeyen araç konumu yanıtı")
    metin = html.unescape(m.group(1)).strip()
    return json.loads(metin) if metin else []


def satirlari_hazirla(zaman):
    """E-tablonun Araçlar sekmesindeki 11 sütunla birebir aynı sırada satırlar."""
    bizim = DURAKLAR[("D", DURAK)]
    try:
        araclar = araclari_getir()
    except Exception as e:
        return [[zaman, "VERİ ALINAMADI", "", "", "", "", "", "", "", "", ""]], str(e)
    satirlar = []
    for a in araclar:
        enlem, boylam = sayi(a.get("enlem")), sayi(a.get("boylam"))
        yakin_kod = a.get("yakinDurakKodu") or ""
        yakin = durak_bul(yakin_kod, a.get("guzergahkodu"))
        satirlar.append([
            zaman, a.get("kapino") or "", a.get("yon") or "", a.get("guzergahkodu") or "", yakin_kod,
            str(yakin["sira"]) if yakin else "", yakin.get("ad", ""),
            mesafe_m(bizim["enlem"], bizim["boylam"], enlem, boylam),
            enlem if enlem is not None else "", boylam if boylam is not None else "",
            a.get("son_konum_zamani") or "",
        ])
    if not satirlar:
        satirlar.append([zaman, "Araç yok", "", "", "", "", "", "", "", "", ""])
    return satirlar, None


def gonder(satirlar):
    adres = os.environ.get("WEB_APP_URL", "").strip()
    if not adres:
        for s in satirlar:
            print("   ", " | ".join(str(h) for h in s))
        return
    govde = json.dumps({"anahtar": os.environ.get("GIZLI_ANAHTAR", "").strip(), "satirlar": satirlar},
                       ensure_ascii=False).encode("utf-8")
    # Apps Script önce isteği işler, sonra sonucu başka bir adrese yönlendirir; urllib bunu kendisi izler
    yanit = json.loads(istek(adres, veri=govde, basliklar={"Content-Type": "application/json"}))
    if not yanit.get("ok"):
        raise RuntimeError("e-tablo kabul etmedi: %s" % yanit.get("hata"))


def bir_kayit():
    zaman = simdi().strftime("%Y-%m-%d %H:%M:%S")
    satirlar, ibb_hatasi = satirlari_hazirla(zaman)
    gonder(satirlar)
    durum = "İBB'ye ulaşılamadı: " + ibb_hatasi if ibb_hatasi else "%d araç" % (
        0 if satirlar[0][1] == "Araç yok" else len(satirlar))
    print("%s  %s" % (zaman, durum), flush=True)
    return ibb_hatasi is None


def main():
    if "--deneme" in sys.argv:
        print("Deneme kaydı (saat aralığına bakılmadan):")
        try:
            return 0 if bir_kayit() else 1
        except Exception as e:
            print("HATA: %s" % e)
            return 1

    print("Kayıt %s-%s arası her dakika alınacak. Başlangıç: %s" % (
        BASLANGIC, BITIS, simdi().strftime("%H:%M:%S")), flush=True)
    hata_sayisi = 0
    while simdi().strftime("%H:%M") <= BITIS:
        if simdi().strftime("%H:%M") >= BASLANGIC:
            try:
                if not bir_kayit():
                    hata_sayisi += 1
            except Exception as e:
                hata_sayisi += 1
                print("%s  HATA: %s" % (simdi().strftime("%H:%M:%S"), e), flush=True)
        time.sleep(60 - time.time() % 60)  # bir sonraki tam dakikaya kadar bekle

    print("Bitti. Hatalı dakika sayısı: %d" % hata_sayisi)
    # Çok fazla hata varsa GitHub işi başarısız sayar ve sana e-posta atar
    return 1 if hata_sayisi > 15 else 0


if __name__ == "__main__":
    sys.exit(main())
