
# Eval report — arm: llm (qwen2.5:1.5b-instruct-q4_K_M)

## Metrics

| condition | hcpcs_f1 | taxonomy_f1 |
|---|---|---|
| breast-cancer | 0.400 | 0.207 |
| carpal-tunnel-syndrome | 0.080 | 0.182 |
| cataract | 0.154 | 0.750 |
| high-blood-pressure | 0.000 | 0.000 |
| migraine | 0.000 | 0.200 |
| piriformis-syndrome | 0.267 | 0.333 |
| rotator-cuff-tear | 0.154 | 0.452 |
| tennis-elbow | 0.385 | 0.296 |
| type-2-diabetes | 0.000 | 0.148 |
| ulcer | 0.000 | 0.000 |
| **mean** | **0.144** | **0.257** |

## Qualitative side-by-side

### breast-cancer

**HCPCS (predicted):** 0045U, 0295U, 0546T, 19081, 19082, 19083, 19084, 19085, 19086, 19100, 19101, 19294, 38530, 77063, 77065

**HCPCS (gold):** 19081, 19083, 19085, 19100, 19301, 19303, 19307, 19318, 77063, 77065, 77066, 77067, 77338, 96413, 96417

**Taxonomy (predicted):** 204E00000X, 204F00000X, 207RX0202X, 207XP3100X, 207XS0106X, 207XS0114X, 207XS0117X, 207XX0004X, 207XX0801X, 207YX0007X, 208200000X, 2082S0099X, 2082S0105X, 208600000X, 2086S0105X, 2086S0120X, 2086S0122X, 2086S0127X, 2086S0129X, 2086X0206X

**Taxonomy (gold):** 207RH0003X, 207RX0202X, 207VX0201X, 208200000X, 2085R0001X, 2085R0202X, 2085R0203X, 2086X0206X, 261QR0206X

**CMS specialties (predicted):** Cardiac Surgery, Colorectal Surgery (Proctology), General Surgery, Gynecological Oncology, Hand Surgery, Hematology-Oncology, Maxillofacial Surgery, Medical Oncology, Micrographic Dermatologic Surgery, Neurosurgery, Oral Surgery (Dentist only), Orthopedic Surgery, Plastic and Reconstructive Surgery, Radiation Oncology, Surgical Oncology, Thoracic Surgery, Vascular Surgery

**CMS specialties (gold):** Diagnostic Radiology, Radiation Oncology, Medical Oncology, Hematology-Oncology, Surgical Oncology, General Surgery, Plastic and Reconstructive Surgery, Gynecological Oncology, Obstetrics & Gynecology

**PubMed queries (predicted):** breast cancer, mammary carcinoma, gynecomastia, palpable mass, breast surgery, breast chemotherapy, breast radiation therapy, breast biopsy, breast lumpectomy, breast mastectomy, breast endocrine treatment, breast targeted therapy

**PubMed queries (gold):** breast cancer, breast cancer screening, mammography screening, breast cancer surgery, breast cancer chemotherapy, breast cancer radiation therapy, mastectomy outcomes, lumpectomy breast conserving surgery, sentinel lymph node biopsy breast cancer, HER2 positive breast cancer, triple negative breast cancer, breast cancer survival outcomes

### carpal-tunnel-syndrome

**HCPCS (predicted):** 01830, 01832, 20526, 25031, 25040, 25085, 25101, 25105, 25107, 25320, 25332, 25337, 25446, 25449, 25520

**HCPCS (gold):** 20526, 29848, 64718, 64721, 76882, 95860, 95886, 95905, 99213, 99214

**Taxonomy (predicted):** 111NN0400X, 2084A0401X, 2084A2900X, 2084B0002X, 2084B0040X, 2084D0003X, 2084E0001X, 2084F0202X, 2084H0002X, 2084N0008X, 2084N0400X, 2084N0402X, 2084N0600X, 2084P0005X, 2084P0015X, 2084P0301X, 2084P0800X, 2084P0802X, 2084P0804X, 2084V0102X

**Taxonomy (gold):** 207T00000X, 207X00000X, 207XP3100X, 207XS0106X, 207XS0114X, 208100000X, 2081N0008X, 2081P2900X, 208200000X, 2082S0105X, 2084N0008X, 2084N0400X, 2084N0600X

**CMS specialties (predicted):** Hand Surgery, Neurology, Orthopedic Surgery

**CMS specialties (gold):** Hand Surgery, Orthopedic Surgery, Neurology, Physical Medicine and Rehabilitation, Plastic and Reconstructive Surgery, Neurosurgery

**PubMed queries (predicted):** carpal tunnel syndrome, median nerve compression, wrist pain, carpal tunnel nerve block, carpal tunnel ultrasound guidance, carpal tunnel electromyography, carpal tunnel tunnel decompression, carpal tunnel surgical release, carpal tunnel percutaneous injection, median nerve nerve block, median nerve ultrasound guidance, median nerve electromyography

**PubMed queries (gold):** carpal tunnel syndrome, carpal tunnel release, median nerve entrapment, endoscopic carpal tunnel release, carpal tunnel steroid injection, nerve conduction study carpal tunnel, ultrasound diagnosis carpal tunnel, median nerve decompression, carpal tunnel surgery outcomes, carpal tunnel physical therapy, revision carpal tunnel release, carpal tunnel syndrome electrodiagnosis

### cataract

**HCPCS (predicted):** 00144, 00147, 0616T, 0617T, 0618T, 65210, 65280, 65285, 65286, 66160, 66987, 66988, 67331, 67335, 67909

**HCPCS (gold):** 66982, 66984, 66985, 66987, 66988, 76519, 92002, 92004, 92012, 92014, V2632

**Taxonomy (predicted):** 207W00000X, 207WX0009X, 207WX0107X, 207WX0108X, 207WX0109X, 207WX0110X, 207WX0120X, 207WX0200X

**Taxonomy (gold):** 152W00000X, 152WC0802X, 207W00000X, 207WX0009X, 207WX0107X, 207WX0110X, 207WX0120X, 207WX0200X

**CMS specialties (predicted):** Ophthalmology

**CMS specialties (gold):** Ophthalmology, Optometry

**PubMed queries (predicted):** cataract, cloudy lens, age-related macular degeneration, ophthalmology, eye surgery, eye laser treatment, eye phacoemulsification, eye intracapsular cataract extraction, iris surgery, iris laser treatment, iris phacoemulsification, iris intracapsular cataract extraction

**PubMed queries (gold):** cataract surgery, phacoemulsification, intraocular lens implantation, cataract extraction, premium intraocular lens, femtosecond laser assisted cataract surgery, toric intraocular lens, multifocal intraocular lens, posterior capsular opacification, cataract surgery outcomes, cataract complications, IOL power calculation

### high-blood-pressure

**HCPCS (predicted):** 0001F, 00216, 00352, 00560, 00562, 00563, 01916, 0501T, 0502T, 0503T, 0504T, 0523T, 0623T, 75574, 93355

**HCPCS (gold):** 80053, 80061, 81003, 82947, 83036, 93000, 93005, 93010, 93784, 93786, 93788, 93790, 99202, 99203, 99204, 99205, 99212, 99213, 99214, 99215

**Taxonomy (predicted):** 111NN0400X, 207RA0001X, 207RI0011X, 207UN0901X, 207VE0102X, 2084A0401X, 2084A2900X, 2084B0002X, 2084B0040X, 2084D0003X, 2084E0001X, 2084F0202X, 2084H0002X, 2084N0008X, 2084N0400X, 2084N0402X, 2084N0600X, 2084P0005X, 2084P0015X, 2084V0102X

**Taxonomy (gold):** 207Q00000X, 207R00000X, 207RC0000X, 207RE0101X, 207RN0300X, 208D00000X

**CMS specialties (predicted):** Advanced Heart Failure and Transplant Cardiology, Cardiology, Endocrinology, Interventional Cardiology, Nephrology, Neurology

**CMS specialties (gold):** Internal Medicine, Family Practice, Cardiology, Nephrology, Endocrinology, General Practice

**PubMed queries (predicted):** hypertension, high bp, blood pressure elevation, high blood pressure, arterial hypertension, cardiovascular disease risk factors, heart medication management, heart lifestyle changes, heart diuretics, heart antihypertensive drugs, heart vasodilators, heart therapeutic diets

**PubMed queries (gold):** hypertension management, essential hypertension treatment, resistant hypertension, antihypertensive therapy, ambulatory blood pressure monitoring, hypertension guidelines, hypertensive crisis treatment, blood pressure control primary care, renovascular hypertension, secondary hypertension workup, chronic kidney disease hypertension, hypertension cardiovascular outcomes

### migraine

**HCPCS (predicted):** 00210, 00211, 00212, 00216, 00218, 00220, 00222, 0042T, 01926, 01933, 0398T, 31290, 31291, 33370, 61595

**HCPCS (gold):** 64400, 64405, 64505, 64615, 99202, 99203, 99204, 99213, 99214, 99215, J0585

**Taxonomy (predicted):** 2084A0401X, 2084A2900X, 2084B0002X, 2084B0040X, 2084D0003X, 2084E0001X, 2084F0202X, 2084H0002X, 2084N0008X, 2084N0400X, 2084N0402X, 2084N0600X, 2084P0005X, 2084P0015X, 2084P0301X, 2084P0800X, 2084P0802X, 2084P0804X, 2084P0805X, 2084V0102X

**Taxonomy (gold):** 207LP2900X, 207Q00000X, 207R00000X, 2081P2900X, 2084N0400X, 2084N0402X, 2084P2900X, 2084V0102X, 208VP0000X, 208VP0014X

**CMS specialties (predicted):** Advanced Heart Failure and Transplant Cardiology, Cardiology, Geriatric Psychiatry, Interventional Cardiology, Neurology, Neuropsychiatry, Psychiatry

**CMS specialties (gold):** Neurology, Pain Management, Interventional Pain Management, Internal Medicine, Family Practice, Anesthesiology

**PubMed queries (predicted):** migraine, headache, unspecified type, rebound headache, migraine headache, cerebral vascular disorder, neurovascular pathology, brain analgesic injection, brain triptans, brain beta-blockers, brain steroids, brain vasodilators, brain antiemetics

**PubMed queries (gold):** migraine, chronic migraine, migraine botulinum toxin, occipital nerve block migraine, migraine prophylaxis, CGRP migraine, episodic migraine treatment, migraine headache management, triptans migraine, migraine prevention, chronic migraine botox, migraine pathophysiology

### piriformis-syndrome

**HCPCS (predicted):** 00300, 15958, 20552, 20553, 27045, 27087, 27096, 27100, 27105, 27110, 64445, 64446, 76932, 77003, G0260

**HCPCS (gold):** 20552, 20553, 27096, 64450, 64493, 64640, 76942, 77003, 95907, 95908, 95909, 95910, 95911, 95912, 95913

**Taxonomy (predicted):** 111NN0400X, 111NX0800X, 204C00000X, 207L00000X, 207LA0401X, 207LC0200X, 207LH0002X, 207LP2900X, 207LP3000X, 208100000X, 2081H0002X, 2081S0010X, 2084A0401X, 2084B0040X, 2084D0003X, 2084E0001X, 2084N0400X, 2084N0402X, 2084S0010X, 2084V0102X

**Taxonomy (gold):** 204C00000X, 207LP2900X, 207T00000X, 207X00000X, 207XP3100X, 207XS0114X, 208100000X, 2081P0010X, 2081P2900X, 2081S0010X, 2084N0400X, 2084N0402X, 2084P0800X, 2084P0805X, 2085R0001X, 208600000X

**CMS specialties (predicted):** Anesthesiology, Anesthesiology Assistant, Dental Anesthesiology, Interventional Pain Management, Interventional Radiology, Neurology, Orthopedic Surgery, Pain Management, Physical Medicine and Rehabilitation, Sports Medicine

**CMS specialties (gold):** Physical Medicine and Rehabilitation, Neurology, Orthopedic Surgery, Neurological Surgery, Sports Medicine, Interventional Radiology, Interventional Pain Management, Osteopathic Manipulative Medicine, Neuromuscular Medicine

**PubMed queries (predicted):** piriformis syndrome, deep gluteal syndrome, extraspinal sciatica, piriformis muscle syndrome, sciatica, nerve compression syndromes, piriformis trigger point, piriformis nerve conduction, piriformis nerve block, piriformis ultrasonic guidance, piriformis fluoroscopic guidance, piriformis facet joint

**PubMed queries (gold):** piriformis syndrome, piriformis muscle injection, piriformis release surgery, deep gluteal syndrome, piriformis botulinum toxin, piriformis sciatica, piriformis entrapment, sciatic nerve piriformis, piriformis MRI diagnosis, piriformis electrophysiology, extraspinal sciatica piriformis

### rotator-cuff-tear

**HCPCS (predicted):** 0439T, 20500, 20501, 20550, 20551, 20552, 20553, 20600, 20604, 20605, 20606, 20610, 20611, 23350, C9781

**HCPCS (gold):** 20610, 20611, 23410, 23412, 23420, 29807, 29822, 29823, 29824, 29826, 29827

**Taxonomy (predicted):** 103TR0400X, 111NR0400X, 152WL0500X, 204C00000X, 207PS0010X, 207QS0010X, 207RS0010X, 207XX0005X, 2080S0010X, 208100000X, 2081H0002X, 2081N0008X, 2081P0004X, 2081P0010X, 2081P0301X, 2081P2900X, 2081S0010X, 225400000X, 225C00000X, 273Y00000X

**Taxonomy (gold):** 204C00000X, 207PS0010X, 207QS0010X, 207RS0010X, 207X00000X, 207XS0106X, 207XS0114X, 207XX0005X, 207XX0801X, 208100000X, 2081S0010X

**CMS specialties (predicted):** Intensive Cardiac Rehabilitation, Orthopedic Surgery, Physical Medicine and Rehabilitation, Sports Medicine

**CMS specialties (gold):** Orthopedic Surgery, Sports Medicine, Hand Surgery, Physical Medicine and Rehabilitation

**PubMed queries (predicted):** rotator cuff tear, shoulder impingement syndrome, subacromial bursitis, shoulder arthroscopy, shoulder debridement, shoulder surgical repair, shoulder laser therapy, shoulder injection, shoulder ultrasound guidance, cuff arthroscopy, cuff debridement, cuff surgical repair

**PubMed queries (gold):** rotator cuff tear, rotator cuff repair, arthroscopic rotator cuff repair, rotator cuff tendinopathy, subacromial decompression, shoulder impingement syndrome, supraspinatus tear, rotator cuff MRI diagnosis, rotator cuff surgery outcomes, rotator cuff rehabilitation, partial rotator cuff tear, massive rotator cuff tear

### tennis-elbow

**HCPCS (predicted):** 01732, 20550, 20551, 20612, 23405, 23406, 23935, 24000, 24006, 24310, 24357, 24358, 24359, 25290, 27006

**HCPCS (gold):** 0101T, 0102T, 0232T, 20550, 20551, 24357, 24358, 24359, 29837, 29838, 76942

**Taxonomy (predicted):** 111NX0800X, 1223X0400X, 163WX0800X, 204C00000X, 207PS0010X, 207QS0010X, 207RS0010X, 207XX0005X, 2080S0010X, 208100000X, 2081H0002X, 2081N0008X, 2081P0004X, 2081P0010X, 2081P0301X, 2081P2900X, 2081S0010X, 2083S0010X, 2084S0010X, 213ES0000X

**Taxonomy (gold):** 204C00000X, 207X00000X, 207XS0114X, 207XX0004X, 208100000X, 2081P2900X, 2081S0010X

**CMS specialties (predicted):** Orthopedic Surgery, Physical Medicine and Rehabilitation, Sports Medicine

**CMS specialties (gold):** Orthopedic Surgery, Sports Medicine, Physical Medicine and Rehabilitation, Hand Surgery, Interventional Radiology

**PubMed queries (predicted):** tennis elbow, lateral epicondylitis, lateral elbow tendinopathy, extensor carpi radialis brevis tendinopathy, tendinopathy, elbow injection, elbow incision, elbow tenotomy, elbow shock wave, elbow debridement, elbow arthroscopy, elbow endoscope

**PubMed queries (gold):** lateral epicondylitis, tennis elbow, tennis elbow injection, lateral epicondylitis corticosteroid, lateral epicondylitis platelet rich plasma, tennis elbow shockwave therapy, lateral epicondylitis surgery, lateral epicondyle tenotomy, extensor carpi radialis brevis tendinopathy, chronic lateral elbow tendinopathy, tennis elbow physical therapy, lateral epicondylitis arthroscopy

### type-2-diabetes

**HCPCS (predicted):** 00732, 00794, 48100, 48102, 48120, 48140, 48145, 48146, 48150, 48152, 48153, 48154, 48155, 48510, 48520

**HCPCS (gold):** 80053, 80061, 82043, 82570, 82947, 83036, 97802, 97803, 99202, 99203, 99204, 99213, 99214, 99215, G0108, G0109, G0270

**Taxonomy (predicted):** 133VN1201X, 163WN0300X, 163WR1000X, 1835C0206X, 207QB0002X, 207RA0001X, 207RB0002X, 207RE0101X, 207RI0011X, 207RN0300X, 207UN0901X, 207VB0002X, 207VE0102X, 2080B0002X, 2080P0202X, 2080P0205X, 2080P0210X, 2083B0002X, 2084B0002X, 246W00000X

**Taxonomy (gold):** 207Q00000X, 207R00000X, 207RE0101X, 207RN0300X, 207W00000X, 208D00000X, 213E00000X

**CMS specialties (predicted):** Advanced Heart Failure and Transplant Cardiology, Cardiology, Endocrinology, Interventional Cardiology, Nephrology

**CMS specialties (gold):** Endocrinology, Internal Medicine, Family Practice, General Practice, Nephrology, Ophthalmology, Podiatry

**PubMed queries (predicted):** type 2 diabetes, non-insulin-dependent diabetes mellitus, adult-onset diabetes, type 2 diabetes mellitus, non-insulin-dependent diabetes, hyperglycemia, insulin resistance, pancreas insulin therapy, pancreas oral hypoglycemic agents, pancreas diet management, pancreas exercise, pancreas foot care

**PubMed queries (gold):** type 2 diabetes management, diabetes hemoglobin a1c, insulin therapy type 2 diabetes, metformin type 2 diabetes, GLP-1 receptor agonists diabetes, diabetic nephropathy, diabetic retinopathy screening, diabetes self management education, glycemic control type 2 diabetes, diabetic neuropathy, diabetes cardiovascular outcomes, continuous glucose monitoring type 2 diabetes

### ulcer

**HCPCS (predicted):** 00190, 00192, 00216, 00300, 00352, 00400, 00560, 00562, 00563, 0061U, 0075T, 00770, 0090U, 01250, 96574

**HCPCS (gold):** 43235, 43239, 43247, 43250, 43253, 43255, 83013, 86677, 87338, 99204, 99205, 99213, 99214, 99215

**Taxonomy (predicted):** 111NX0800X, 1223X0400X, 1835E0208X, 207N00000X, 207ND0101X, 207ND0900X, 207NI0002X, 207NP0225X, 207NS0135X, 207P00000X, 207PE0004X, 207PE0005X, 207PH0002X, 207PP0204X, 207PS0010X, 207PT0002X, 2080P0204X, 208600000X, 2086S0129X, 208G00000X

**Taxonomy (gold):** 207Q00000X, 207R00000X, 207RG0100X, 2080P0206X, 208D00000X

**CMS specialties (predicted):** Dermatology, Emergency Medicine, Vascular Surgery

**CMS specialties (gold):** Gastroenterology, Internal Medicine, Family Practice, General Practice

**PubMed queries (predicted):** ulcer, open wound, pressure sore, gangrene, pressure ulcer, venous thrombosis, skin debridement, skin surgical excision, skin sterilization, skin compression therapy, skin plasma dressing, skin antibiotics

**PubMed queries (gold):** peptic ulcer disease, gastric ulcer, duodenal ulcer, helicobacter pylori eradication, proton pump inhibitor ulcer, upper endoscopy peptic ulcer, nsaid induced peptic ulcer, bleeding peptic ulcer, esophagogastroduodenoscopy, h pylori treatment regimen, stress ulcer prophylaxis, peptic ulcer epidemiology

