
# Eval report — arm: llm (qwen2.5:3b-instruct-q4_K_M)

## Metrics

| condition | hcpcs_f1 | taxonomy_f1 |
|---|---|---|
| breast-cancer | 0.267 | 0.357 |
| carpal-tunnel-syndrome | 0.000 | 0.242 |
| cataract | 0.000 | 0.750 |
| high-blood-pressure | 0.000 | 0.231 |
| migraine | 0.000 | 0.200 |
| piriformis-syndrome | 0.267 | 0.333 |
| rotator-cuff-tear | 0.308 | 0.452 |
| tennis-elbow | 0.385 | 0.296 |
| type-2-diabetes | 0.000 | 0.148 |
| ulcer | 0.069 | 0.160 |
| **mean** | **0.129** | **0.317** |

## Qualitative side-by-side

### breast-cancer

**HCPCS (predicted):** 00402, 19081, 19082, 19083, 19084, 19085, 19086, 19100, 19101, 19294, 19340, 19342, 19357, 19361, 38530

**HCPCS (gold):** 19081, 19083, 19085, 19100, 19301, 19303, 19307, 19318, 77063, 77065, 77066, 77067, 77338, 96413, 96417

**Taxonomy (predicted):** 125Q00000X, 133VN1301X, 163WP0218X, 163WX0200X, 1835X0200X, 207RH0003X, 207RX0202X, 207VX0201X, 207Y00000X, 207YX0007X, 2080P0207X, 2082S0099X, 2085R0001X, 208600000X, 2086X0206X, 261QX0200X, 261QX0203X, 364SX0200X, 364SX0204X

**Taxonomy (gold):** 207RH0003X, 207RX0202X, 207VX0201X, 208200000X, 2085R0001X, 2085R0202X, 2085R0203X, 2086X0206X, 261QR0206X

**CMS specialties (predicted):** Gynecological Oncology, Hematology-Oncology, Medical Oncology, Radiation Oncology, Surgical Oncology

**CMS specialties (gold):** Diagnostic Radiology, Radiation Oncology, Medical Oncology, Hematology-Oncology, Surgical Oncology, General Surgery, Plastic and Reconstructive Surgery, Gynecological Oncology, Obstetrics & Gynecology

**PubMed queries (predicted):** breast cancer, ductal carcinoma in situ, lobular carcinoma in situ, invasive ductal carcinoma, invasive lobular carcinoma, breast biopsy, breast mastectomy, breast lumpectomy, breast radiation therapy, breast chemotherapy, breast endocrine therapy, breast targeted therapy

**PubMed queries (gold):** breast cancer, breast cancer screening, mammography screening, breast cancer surgery, breast cancer chemotherapy, breast cancer radiation therapy, mastectomy outcomes, lumpectomy breast conserving surgery, sentinel lymph node biopsy breast cancer, HER2 positive breast cancer, triple negative breast cancer, breast cancer survival outcomes

### carpal-tunnel-syndrome

**HCPCS (predicted):** 23405, 23406, 23935, 24000, 24006, 24101, 24310, 24357, 24358, 24359, 25000, 25001, 25020, 25023, 25290

**HCPCS (gold):** 20526, 29848, 64718, 64721, 76882, 95860, 95886, 95905, 99213, 99214

**Taxonomy (predicted):** 111NN0400X, 111NX0800X, 208100000X, 2081H0002X, 2081N0008X, 2081P0004X, 2081P0010X, 2081P0301X, 2081P2900X, 2081S0010X, 2084A0401X, 2084A2900X, 2084B0002X, 2084B0040X, 2084D0003X, 2084E0001X, 2084F0202X, 2084N0400X, 2084N0402X, 2084V0102X

**Taxonomy (gold):** 207T00000X, 207X00000X, 207XP3100X, 207XS0106X, 207XS0114X, 208100000X, 2081N0008X, 2081P2900X, 208200000X, 2082S0105X, 2084N0008X, 2084N0400X, 2084N0600X

**CMS specialties (predicted):** Hand Surgery, Neurology, Orthopedic Surgery, Physical Medicine and Rehabilitation

**CMS specialties (gold):** Hand Surgery, Orthopedic Surgery, Neurology, Physical Medicine and Rehabilitation, Plastic and Reconstructive Surgery, Neurosurgery

**PubMed queries (predicted):** carpal tunnel syndrome, cubital tunnel syndrome, median nerve compression, median neuropathy at the wrist, wrist block, wrist incision, wrist arthroscopy, wrist ulnar nerve decompression, wrist tenotomy, wrist platelet rich plasma, wrist immobilization, median nerve block

**PubMed queries (gold):** carpal tunnel syndrome, carpal tunnel release, median nerve entrapment, endoscopic carpal tunnel release, carpal tunnel steroid injection, nerve conduction study carpal tunnel, ultrasound diagnosis carpal tunnel, median nerve decompression, carpal tunnel surgery outcomes, carpal tunnel physical therapy, revision carpal tunnel release, carpal tunnel syndrome electrodiagnosis

### cataract

**HCPCS (predicted):** 00144, 00147, 0616T, 0617T, 0618T, 65235, 65920, 66160, 66500, 66505, 66625, 66630, 66635, 66680, 66682

**HCPCS (gold):** 66982, 66984, 66985, 66987, 66988, 76519, 92002, 92004, 92012, 92014, V2632

**Taxonomy (predicted):** 207W00000X, 207WX0009X, 207WX0107X, 207WX0108X, 207WX0109X, 207WX0110X, 207WX0120X, 207WX0200X

**Taxonomy (gold):** 152W00000X, 152WC0802X, 207W00000X, 207WX0009X, 207WX0107X, 207WX0110X, 207WX0120X, 207WX0200X

**CMS specialties (predicted):** Ophthalmology

**CMS specialties (gold):** Ophthalmology, Optometry

**PubMed queries (predicted):** cataract, clouded lens, opacity of the lens, ophthalmology, eye phacoemulsification, eye surgical removal, eye intraocular lens implantation, eye capsulotomy, eye excimer laser ablation, lens phacoemulsification, lens surgical removal, lens intraocular lens implantation

**PubMed queries (gold):** cataract surgery, phacoemulsification, intraocular lens implantation, cataract extraction, premium intraocular lens, femtosecond laser assisted cataract surgery, toric intraocular lens, multifocal intraocular lens, posterior capsular opacification, cataract surgery outcomes, cataract complications, IOL power calculation

### high-blood-pressure

**HCPCS (predicted):** 99474

**HCPCS (gold):** 80053, 80061, 81003, 82947, 83036, 93000, 93005, 93010, 93784, 93786, 93788, 93790, 99202, 99203, 99204, 99205, 99212, 99213, 99214, 99215

**Taxonomy (predicted):** 207R00000X, 207RA0000X, 207RA0001X, 207RA0002X, 207RA0201X, 207RA0401X, 207RB0002X, 207RC0000X, 207RC0001X, 207RC0200X, 207RE0101X, 207RG0100X, 207RG0300X, 207RH0000X, 207RH0002X, 207RH0003X, 207RH0005X, 207RI0001X, 207RI0008X, 207RI0011X

**Taxonomy (gold):** 207Q00000X, 207R00000X, 207RC0000X, 207RE0101X, 207RN0300X, 208D00000X

**CMS specialties (predicted):** Advanced Heart Failure and Transplant Cardiology, Cardiology, Internal Medicine, Interventional Cardiology

**CMS specialties (gold):** Internal Medicine, Family Practice, Cardiology, Nephrology, Endocrinology, General Practice

**PubMed queries (predicted):** high blood pressure, hypertension, blood pressure, cardiovascular diseases

**PubMed queries (gold):** hypertension management, essential hypertension treatment, resistant hypertension, antihypertensive therapy, ambulatory blood pressure monitoring, hypertension guidelines, hypertensive crisis treatment, blood pressure control primary care, renovascular hypertension, secondary hypertension workup, chronic kidney disease hypertension, hypertension cardiovascular outcomes

### migraine

**HCPCS (predicted):** 01991, 61595, 61791, 64555, 64575, 64640, 64784, 64790, 64792, 64856, 64857, 64859, 92640, 95971, 95972

**HCPCS (gold):** 64400, 64405, 64505, 64615, 99202, 99203, 99204, 99213, 99214, 99215, J0585

**Taxonomy (predicted):** 111NN0400X, 2084A0401X, 2084A2900X, 2084B0002X, 2084B0040X, 2084D0003X, 2084E0001X, 2084F0202X, 2084H0002X, 2084N0008X, 2084N0400X, 2084N0402X, 2084N0600X, 2084P0005X, 2084P0015X, 2084P0301X, 2084P0800X, 2084P0802X, 2084P0804X, 2084V0102X

**Taxonomy (gold):** 207LP2900X, 207Q00000X, 207R00000X, 2081P2900X, 2084N0400X, 2084N0402X, 2084P2900X, 2084V0102X, 208VP0000X, 208VP0014X

**CMS specialties (predicted):** Interventional Pain Management, Neurology, Pain Management

**CMS specialties (gold):** Neurology, Pain Management, Interventional Pain Management, Internal Medicine, Family Practice, Anesthesiology

**PubMed queries (predicted):** migraine, chronic migraine, cluster headache, sinus headache, migraine headache, brainstem transcranial magnetic stimulation, brainstem intranasal spray, brainstem photobiomodulation, brainstem trigger point injection, brainstem nerve block, brainstem endoscopy, brainstem ultrasound guidance

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

**HCPCS (predicted):** 01472, 01652, 01714, 20550, 20551, 20612, 23101, 23130, 23350, 23410, 23412, 23420, 26390, 29827, C9781

**HCPCS (gold):** 20610, 20611, 23410, 23412, 23420, 29807, 29822, 29823, 29824, 29826, 29827

**Taxonomy (predicted):** 111NX0800X, 1223X0400X, 163WP0000X, 163WX0800X, 204C00000X, 207PS0010X, 207QS0010X, 207RS0010X, 207XX0005X, 2080S0010X, 208100000X, 2081H0002X, 2081N0008X, 2081P0004X, 2081P0010X, 2081P0301X, 2081P2900X, 2081S0010X, 2083S0010X, 2084S0010X

**Taxonomy (gold):** 204C00000X, 207PS0010X, 207QS0010X, 207RS0010X, 207X00000X, 207XS0106X, 207XS0114X, 207XX0005X, 207XX0801X, 208100000X, 2081S0010X

**CMS specialties (predicted):** Interventional Pain Management, Orthopedic Surgery, Pain Management, Physical Medicine and Rehabilitation, Sports Medicine

**CMS specialties (gold):** Orthopedic Surgery, Sports Medicine, Hand Surgery, Physical Medicine and Rehabilitation

**PubMed queries (predicted):** rotator cuff injury, shoulder instability, supraspinatus tendonopathy, tendinopathy, shoulder arthroscopy, shoulder debridement, shoulder repair, shoulder suture, shoulder implant, shoulder injection, shoulder shock wave, shoulder platelet rich plasma

**PubMed queries (gold):** rotator cuff tear, rotator cuff repair, arthroscopic rotator cuff repair, rotator cuff tendinopathy, subacromial decompression, shoulder impingement syndrome, supraspinatus tear, rotator cuff MRI diagnosis, rotator cuff surgery outcomes, rotator cuff rehabilitation, partial rotator cuff tear, massive rotator cuff tear

### tennis-elbow

**HCPCS (predicted):** 01732, 20550, 20551, 20612, 23405, 23406, 23935, 24000, 24006, 24310, 24357, 24358, 24359, 25290, 27006

**HCPCS (gold):** 0101T, 0102T, 0232T, 20550, 20551, 24357, 24358, 24359, 29837, 29838, 76942

**Taxonomy (predicted):** 111NX0800X, 1223X0400X, 163WX0800X, 204C00000X, 207PS0010X, 207QS0010X, 207RS0010X, 207XS0106X, 207XX0005X, 2080S0010X, 208100000X, 2081H0002X, 2081N0008X, 2081P0004X, 2081P0010X, 2081P0301X, 2081P2900X, 2081S0010X, 2083S0010X, 2084S0010X

**Taxonomy (gold):** 204C00000X, 207X00000X, 207XS0114X, 207XX0004X, 208100000X, 2081P2900X, 2081S0010X

**CMS specialties (predicted):** Hand Surgery, Orthopedic Surgery, Physical Medicine and Rehabilitation, Sports Medicine

**CMS specialties (gold):** Orthopedic Surgery, Sports Medicine, Physical Medicine and Rehabilitation, Hand Surgery, Interventional Radiology

**PubMed queries (predicted):** tennis elbow, lateral epicondylitis, lateral elbow tendinopathy, extensor carpi radialis brevis tendinopathy, tendinopathy, elbow injection, elbow incision, elbow tenotomy, elbow shock wave, elbow debridement, elbow arthroscopy, elbow endoscope

**PubMed queries (gold):** lateral epicondylitis, tennis elbow, tennis elbow injection, lateral epicondylitis corticosteroid, lateral epicondylitis platelet rich plasma, tennis elbow shockwave therapy, lateral epicondylitis surgery, lateral epicondyle tenotomy, extensor carpi radialis brevis tendinopathy, chronic lateral elbow tendinopathy, tennis elbow physical therapy, lateral epicondylitis arthroscopy

### type-2-diabetes

**HCPCS (predicted):** 0330T, 0525T, 36251, 36252, 36253, 36254, 50080, 50081, 50430, 50431, 50432, 50433, 50434, 50435, 50437

**HCPCS (gold):** 80053, 80061, 82043, 82570, 82947, 83036, 97802, 97803, 99202, 99203, 99204, 99213, 99214, 99215, G0108, G0109, G0270

**Taxonomy (predicted):** 152WP0200X, 207R00000X, 207RA0000X, 207RA0001X, 207RA0002X, 207RA0201X, 207RA0401X, 207RB0002X, 207RC0000X, 207RC0001X, 207RC0200X, 207RE0101X, 207RH0002X, 207RH0003X, 207RI0001X, 207RI0008X, 2080C0008X, 2080P0006X, 2080P0205X, 2080P0207X

**Taxonomy (gold):** 207Q00000X, 207R00000X, 207RE0101X, 207RN0300X, 207W00000X, 208D00000X, 213E00000X

**CMS specialties (predicted):** Endocrinology, Internal Medicine

**CMS specialties (gold):** Endocrinology, Internal Medicine, Family Practice, General Practice, Nephrology, Ophthalmology, Podiatry

**PubMed queries (predicted):** type 2 diabetes, adult-onset diabetes, non-insulin-dependent diabetes mellitus, niddm, t2d, type 2 diabetes mellitus, adult-onset diabetes mellitus, pancreas hemoglobin a1c, pancreas fasting plasma glucose, pancreas oral glucose tolerance test, pancreas imaging, pancreas lifestyle counseling

**PubMed queries (gold):** type 2 diabetes management, diabetes hemoglobin a1c, insulin therapy type 2 diabetes, metformin type 2 diabetes, GLP-1 receptor agonists diabetes, diabetic nephropathy, diabetic retinopathy screening, diabetes self management education, glycemic control type 2 diabetes, diabetic neuropathy, diabetes cardiovascular outcomes, continuous glucose monitoring type 2 diabetes

### ulcer

**HCPCS (predicted):** 00731, 00797, 0647T, 0654T, 35121, 35122, 43239, 43242, 43261, 43361, 43605, 47543, 47550, 47553, 48152

**HCPCS (gold):** 43235, 43239, 43247, 43250, 43253, 43255, 83013, 86677, 87338, 99204, 99205, 99213, 99214, 99215

**Taxonomy (predicted):** 1835E0208X, 207P00000X, 207PE0004X, 207PE0005X, 207PH0002X, 207PP0204X, 207PS0010X, 207PT0002X, 207R00000X, 207RA0000X, 207RA0001X, 207RA0002X, 207RA0201X, 207RA0401X, 207RC0001X, 207RG0100X, 207RH0002X, 207RH0003X, 207RI0001X, 207RI0008X

**Taxonomy (gold):** 207Q00000X, 207R00000X, 207RG0100X, 2080P0206X, 208D00000X

**CMS specialties (predicted):** Emergency Medicine, Gastroenterology, General Surgery, Internal Medicine

**CMS specialties (gold):** Gastroenterology, Internal Medicine, Family Practice, General Practice

**PubMed queries (predicted):** ulcer, peptic ulcer disease, gastric ulcer, duodenal ulcer, stomach endoscopy, stomach biopsy, stomach hemostasis, stomach surgery, stomach steroid, stomach proton pump inhibitor, stomach antibiotic, stomach nutritional support

**PubMed queries (gold):** peptic ulcer disease, gastric ulcer, duodenal ulcer, helicobacter pylori eradication, proton pump inhibitor ulcer, upper endoscopy peptic ulcer, nsaid induced peptic ulcer, bleeding peptic ulcer, esophagogastroduodenoscopy, h pylori treatment regimen, stress ulcer prophylaxis, peptic ulcer epidemiology

