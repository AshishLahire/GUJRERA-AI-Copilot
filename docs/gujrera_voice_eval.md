# Voice evaluation

Spoken questions about the demo registry, transcribed on this machine (language as picked in the app) with Whisper small and, for Gujarati and Hindi, AI4Bharat IndicConformer, then sent to the chat. Reproduce with `python scripts/eval_gujrera_voice.py --engines whisper,indic`; the prompts and how to record them are in `docs/gujrera_voice_recording_sheet.md`.

- **WER / CER**: word / character error rate against the prompt text (lower is better).
- **Task success**: the transcript, sent to the chat, gets the expected answer type and cites the expected project, builder or section. This is what matters to a user: a transcript with errors can still be answered correctly.
- **Right name offered**: the heard name was close but not exact, and the chat asked "Did you mean …?" with the right project or builder, so the user gets the answer with one tap (☝️ below).

## Real speakers

No clips yet. Record them with the sheet above.

## Computer voices (English: Windows offline; Gujarati and Hindi: Edge online; much easier than real speech)

| Language | Engine | Clips | WER | CER | Answered right | Right name offered (one tap) | Avg. transcription time |
|:--|:--|:-:|:-:|:-:|:-:|:-:|:-:|
| Gujarati | Whisper small | 10 of 10 | 104% | 69% | 2/10 | 0/10 | 2.8 s |
| Hindi | Whisper small | 10 of 10 | 61% | 39% | 3/10 | 0/10 | 5.7 s |
| English | Whisper small | 10 of 10 | 14% | 6% | 3/10 | 6/10 | 2.1 s |

<details><summary>Every clip</summary>

| ID | Engine | Said | Heard | WER | Task |
|:--|:--|:--|:--|:-:|:-:|
| gu_01 | whisper | અક્ષર વિહાર માં મારા ફ્લેટનું પઝેશન ક્યારે મળશે? | अख्शर विहार मा मारा फलेतनु पजेशन क्यारे मरषे | 100% | ❌ (disambiguate) |
| gu_02 | whisper | ગિરનાર ઓર્કિડ માં મારા ફ્લેટનું પઝેશન ક્યારે મળશે? | जिरनार अर्किड्मा मारा फलेक्नु पाजेशन क्यारे मर्षे | 111% | ❌ (out_of_scope) |
| gu_03 | whisper | સર્જન ટાવર્સ માં મારા ફ્લેટનું પઝેશન ક્યારે મળશે? | सरजन तावर्स मा मारा फलेतनु पजेशन क्यारे मडषे | 100% | ✅ (possession) |
| gu_04 | whisper | બિલ્ડર કેસર બિલ્ડર્સ વિશે જણાવો | Builder Kesar Builder's Vishay Janavu | 100% | ❌ (did_you_mean) |
| gu_05 | whisper | બિલ્ડર આંગણ ડેવલપર્સ વિશે જણાવો | बिल्दर आंगन देवलपर्स विषे जना हो | 100% | ✅ (promoter_profile) |
| gu_06 | whisper | મંગલ સ્ક્વેર ની માહિતી આપો | मंदल स्क्वेर नी माहिती आपो | 100% | ❌ (out_of_scope) |
| gu_07 | whisper | આંગણ આર્કેડ ની માહિતી આપો | आंदर आरकेड नी माहिती आपो | 100% | ❌ (out_of_scope) |
| gu_08 | whisper | પ્રથમ ઓર્કિડ સામે કેટલી ફરિયાદો છે? | प्रत्म और्किद सामे केट्ली फर्यादो चे | 115% | ❌ (disambiguate) |
| gu_09 | whisper | આંગણ એવન્યુ સામે કેટલી ફરિયાદો છે? | आंगर एवन्यू सामे के तली फर्या दो चे | 100% | ❌ (out_of_scope) |
| gu_10 | whisper | રેરા કાયદાની કલમ 18 શું કહે છે? | रेरा काईदानी कलम अदार्षू कहेचे | 110% | ❌ (out_of_scope) |
| hi_01 | whisper | Utsav Residency में मेरे फ्लैट का पज़ेशन कब मिलेगा? | उच्सर्व रेसिटन्सी में मेरे फ्लाट का पजेशन कब मिलेगा? | 47% | ❌ (not_found) |
| hi_02 | whisper | Vasant Plaza में मेरे फ्लैट का पज़ेशन कब मिलेगा? | वसंद प्लाजा में मेरे फ्लाट का पाजेशन कभ मिलेगा? | 53% | ❌ (out_of_scope) |
| hi_03 | whisper | Utsav Square में मेरे फ्लैट का पज़ेशन कब मिलेगा? | उच्सर्व स्क्वेर में मेरे फ्लाट का पुजेशन कब मिलेगा? | 60% | ❌ (not_found) |
| hi_04 | whisper | बिल्डर Prakash Builders के बारे में बताइए | बिल्दर प्रकाश बिल्दर्स के बारे में बताये. | 82% | ✅ (promoter_profile) |
| hi_05 | whisper | बिल्डर Tapi Developers के बारे में बताइए | बिल्डर तापी डवेलपर्स के बारे में बताये. | 55% | ✅ (promoter_profile) |
| hi_06 | whisper | Aangan Enclave की जानकारी दीजिए | आंगन अंक्लेव की जान्कारी दीजीए. | 89% | ✅ (project_profile) |
| hi_07 | whisper | Girnar Residency की जानकारी दीजिए | गिरनार रेसिटन्सी की जानकारी दीजे. | 89% | ❌ (out_of_scope) |
| hi_08 | whisper | Girnar Greens के खिलाफ कितनी शिकायतें हैं? | गिरना और ग्रीन्स के खिलाफ कितनी शिकायते है? | 58% | ❌ (officer_only) |
| hi_09 | whisper | Utsav Plaza के खिलाफ कितनी शिकायतें हैं? | उच्सव प्लाजा के किलाफ कितनी शिकायते है? | 50% | ❌ (officer_only) |
| hi_10 | whisper | रेरा कानून की धारा 18 क्या कहती है? | रेरा कानुन की दारा अथारा क्या कहती है? | 23% | ❌ (out_of_scope) |
| en_01 | whisper | When will I get possession of my flat in Aangan Vihar? | When will I get possession of my flat in Angon, Vihar? | 9% | ☝️ (did_you_mean) |
| en_02 | whisper | When will I get possession of my flat in Sarjan Homes? | When will I get possession of my flat and sergeant homes? | 18% | ☝️ (did_you_mean) |
| en_03 | whisper | When will I get possession of my flat in Mangal Arcade? | When will I get possession of my flat in Mongol arcade? | 9% | ☝️ (did_you_mean) |
| en_04 | whisper | Tell me about the builder Suvarna Builders | Tell me about the builders sovarna builders. | 29% | ☝️ (did_you_mean) |
| en_05 | whisper | Tell me about the builder Girnar Infra | Tell me about the Builder-Gerner Infra. | 14% | ☝️ (did_you_mean) |
| en_06 | whisper | Give me the details of Navrang Elite | Give me the details of Navrang Elite. | 0% | ✅ (project_profile) |
| en_07 | whisper | Give me the details of Aangan Homes | Give me the details of Angan homes. | 14% | ☝️ (did_you_mean) |
| en_08 | whisper | How many complaints are there against Utsav Arcade? | How many complaints are there against Utsav arcade? | 0% | ✅ (complaints) |
| en_09 | whisper | How many complaints are there against Utsav Vihar? | How many complaints are there against its abhihar? | 25% | ❌ (officer_only) |
| en_10 | whisper | What does section eighteen of the RERA Act say about refunds? | What does Section 18 of the RERI Act say about refunds? | 18% | ✅ (legal) |

</details>

Whatever the engine, the app puts the transcript in the text box for the user to check before sending. Computer voices are clean studio speech: the figures that matter are real speakers'.
