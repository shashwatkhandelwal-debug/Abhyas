# One-on-one live run (real models)

- scenes run: 10 of 10; turns per scene: [4, 4, 4, 4, 4, 4, 4, 4, 4, 5]
- end reasons: {'all_correct': 7}; diagnosis verdicts: {'correct': 9, 'wrong': 1}
- fallback_used by role (calls, fallback count, rate):
  - act_tagger: 41 calls, 0 fallbacks, 0%
  - child_voice: 41 calls, 0 fallbacks, 0%
  - coach: 10 calls, 0 fallbacks, 0%
  - diagnosis_classifier: 2 calls, 0 fallbacks, 0%
- word-cap violations: 0
- placeholder leaks: 0
- tokens by model (in, out): {'claude-haiku-5-5': (23778, 9854), 'claude-sonnet-5-5': (9419, 9905)}; estimated spend: US$0.125

## Scene 1: NUM_SUB_REGROUP_BUNDLES / ravi

- diagnosis text: 'रवि बड़ी संख्या में से छोटी घटा देता है, उल्टा कर देता है' -> **correct** (keyword_match, matched=SUB_SMALLER_FROM_LARGER, classifier=False)
- T1 teacher: रवि, तुमने 43 में से 27 कैसे घटाया? एक-एक कदम बताओ।
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - ravi [explain_bug, answer=24] (19 words): दीदी, तो 7 में से 3 घटाया, 4 आया। 4 में से 2 घटाया, 2 आया, तो उत्तर 24!
- T2 teacher: देखो, ये 4 बंडल और 3 खुली तीलियाँ हैं। 3 में से 7 नहीं निकलतीं, तो एक बंडल खोलो और गिनकर बताओ।
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - ravi [scaffolded_correct, answer=16] (18 words): दीदी, 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया, तो उत्तर 16!
- T3 teacher: तुमने पहले 24 कहा था, अब तीलियाँ गिनकर दूसरा उत्तर आया। कौन-सा सही है और क्यों?
  - acts tagged: ['contrast_answers', 'ask_to_explain']  -> child state **CORRECT**
  - ravi [correct_explained, answer=16] (20 words): दीदी, 13 में से 7 घटाया तो 6 आया। 3 में से 2 घटाया तो 1 आया। तो उत्तर 16!
- T4 teacher: बहुत अच्छा। अब ये नया सवाल खुद करो: 52 में से 17।
  - acts tagged: ['give_new_problem']  -> child state **CORRECT**
  - ravi [correct_explained, answer=35] (18 words): दीदी, 12 में से 7 घटाया, 5 आया। 4 में से 1 घटाया, 3 आया। तो उत्तर 35!
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 1, 'checks_on_new_problem': 2}
  - strength: आपने «एक-एक कदम बताओ» कहकर रवि की असली उलझन, यानी 7 में से 3 घटाना, सामने ला दी।
  - change: रवि इकाई में छोटा अंक देखकर उल्टा घटाता है; बंडल उससे खुद बनवाइए और खोलवाइए, फिर 'क्यों' का कारण पूछिए।
  - exact words: तुम 43 तीलियों से बनाओ, फिर बताओ बंडल क्यों खोला?

## Scene 2: NUM_SUB_REGROUP_BUNDLES / priya

- diagnosis text: 'प्रिया ने बंडल खोला पर दहाई में से एक कम करना भूल गई' -> **correct** (keyword_match, matched=SUB_BORROW_NO_DECREMENT, classifier=False)
- T1 teacher: प्रिया, डरो मत, धीरे से बताओ, तुमने 43 में से 27 कैसे किया?
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - priya [explain_bug, answer=26] (21 words): मैडम… 3 के आगे 1 लगाया, 13 में से 7 घटाया, 6 आया। 4 में से 2 घटाया, 2 आया… 26।
- T2 teacher: चलो तीलियों से करते हैं। एक बंडल खोलो, अब कितनी खुली तीलियाँ हैं और कितने बंडल बचे?
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - priya [scaffolded_correct, answer=16] (17 words): दीदी… 13 में से 7 घटाया, 6 आया… 3 में से 2 घटाया, 1 आया… तो 16?
- T3 teacher: तुमने 26 कहा था। बंडल गिनकर देखो, क्या अब भी वही उत्तर आता है?
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - priya [scaffolded_correct, answer=16] (17 words): दीदी… 13 में से 7 घटाया, 6 आया… 3 में से 2 घटाया, 1 आया… तो… 16?
- T4 teacher: शाबाश। अब ये सवाल अकेले करो: 61 में से 28।
  - acts tagged: ['praise_generic', 'give_new_problem']  -> child state **PARTIAL**
  - priya [relapse, answer=43] (22 words): मैडम… 1 के आगे 1 लगाया, 11 में से 8 घटाया, 3 आया। 6 में से 2 घटाया, 4 आया… दीदी, 43।
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'PARTIAL', 'PARTIAL']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 2, 'probes_with_followup': 1, 'checks_on_new_problem': 2}
  - strength: आपने उत्तर बताए बिना कहा «तुमने 26 कहा था। बंडल गिनकर देखो», इससे प्रिया ने खुद दोनों उत्तर परखे।
  - change: नए सवाल में प्रिया दहाई से 1 कम करना फिर भूली; बंडल खोलकर बचे बंडल गिनवाइए और 'क्यों?' पूछिए।
  - exact words: 61 में एक बंडल खोला, तो अब कितने बंडल बचे? यहाँ 6 ही क्यों लिखा?

## Scene 3: NUM_SUB_REGROUP_BUNDLES / aman

- diagnosis text: 'उसे समझ नहीं आया कि क्या करना है' -> **wrong** (no_match, matched=None, classifier=False)
- T1 teacher: अमन, ध्यान से सुनो। तुमने ये कैसे किया, बताओ।
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - aman [explain_bug, answer=20] (23 words): दीदी, 3 में से 7 नहीं घटता... नहीं घटा तो 0 लिख दिया। 4 में से 2 घटाया, 2 आया... तो जवाब 20।
- T2 teacher: देखो, ये तीलियाँ हैं। 3 में से 7 नहीं निकलतीं तो बंडल खोलते हैं। तुम करके दिखाओ।
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - aman [scaffolded_correct, answer=16] (17 words): दीदी... 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया... तो 16।
- T3 teacher: तुम्हारा पहला उत्तर और अब का उत्तर अलग है। कौन सा सही है?
  - acts tagged: ['contrast_answers']  -> child state **CORRECT**
  - aman [correct_explained, answer=16] (21 words): दीदी, 13 में से 7 घटाया तो 6 आया... और 3 में से 2 घटाया तो 1 आया... तो जवाब 16।
- T4 teacher: अब ये नया सवाल: 74 में से 39, खुद करो।
  - acts tagged: ['give_new_problem']  -> child state **CORRECT**
  - aman [correct_explained, answer=35] (21 words): दीदी, 14 में से 9 घटाया तो 5 आया... और 6 में से 3 घटाया तो 3 आया... तो जवाब 35।
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 1, 'checks_on_new_problem': 2}
  - strength: आपने «तुमने ये कैसे किया, बताओ» पूछकर अमन की असली गलती सामने ला दी।
  - change: अमन इकाई में घटाना न हो पाने पर 0 लिखता था; उससे «क्यों?» पूछिए।
  - exact words: अमन, यहाँ 0 क्यों लिखा, और 13 तीलियाँ कहाँ से आईं?

## Scene 4: NUM_ADD_CARRY_BUNDLES / ravi

- diagnosis text: 'रवि हासिल जोड़ना भूल गया' -> **correct** (keyword_match, matched=ADD_CARRY_FORGOTTEN, classifier=False)
- T1 teacher: रवि, तुमने 38 और 45 कैसे जोड़े? पहले इकाई में क्या किया?
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - ravi [explain_bug, answer=73] (20 words): दीदी, 8 और 5 जोड़े, 13 आया। 13 में से 3 लिखा, 3 और 4 जोड़े, 7 आया। तो 73!
- T2 teacher: सब देखो: 3 बंडल 8 तीलियाँ और 4 बंडल 5 तीलियाँ। खुली तीलियाँ मिलाओ, 10 का नया बंडल बाँधो।
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - ravi [scaffolded_correct, answer=83] (18 words): दीदी, 3 लिखा, 1 हासिल ऊपर रखा। 3 और 4 और 1 हासिल जोड़े, 8 आया, तो 83!
- T3 teacher: तुमने 73 कहा था। नया बंडल कहाँ गया? बताओ कौन-सा उत्तर ठीक है?
  - acts tagged: ['contrast_answers', 'ask_to_explain']  -> child state **CORRECT**
  - ravi [correct_explained, answer=83] (18 words): दीदी, 3 लिखा, 1 हासिल ऊपर रखा। 3 और 4 और 1 हासिल जोड़े, 8 आया। तो 83!
- T4 teacher: अब ये करो: 27 और 48।
  - acts tagged: ['give_new_problem']  -> child state **CORRECT**
  - ravi [correct_explained, answer=75] (18 words): दीदी, 5 लिखा, 1 हासिल ऊपर रखा। 2 और 4 और 1 हासिल जोड़े, 7 आया, तो 75!
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 2, 'checks_on_new_problem': 1}
  - strength: आपने शुरू में ही «कैसे जोड़े? पहले इकाई में क्या किया?» पूछा, जिससे रवि का हासिल भूलना साफ़ दिखा।
  - change: रवि से तीलियों के बंडल खुद बनवाइए और 10 खुली तीलियों का नया बंडल उसी से बँधवाइए।
  - exact words: इन तीलियों से 38 और 45 बनाओ, फिर 10 खुली तीलियों का बंडल बाँधो।

## Scene 5: NUM_ADD_CARRY_BUNDLES / priya

- diagnosis text: 'प्रिया ने इकाई का पूरा जोड़ लिख दिया और दहाई का जोड़ आगे रख दिया' -> **correct** (keyword_match, matched=ADD_NO_CARRY, classifier=False)
- T1 teacher: प्रिया, धीरे से बताओ, 713 कैसे आया?
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - priya [explain_bug, answer=713] (20 words): मैडम… 8 और 5 जोड़े, 13 आया। 13 पूरा नीचे लिख दिया। 3 और 4 जोड़े, 7 आया… तो 713।
- T2 teacher: आओ बंडल बनाकर देखते हैं। 8 और 5 तीलियाँ मिलाओ, कितनी हुईं? इनसे एक बंडल बनाओ।
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - priya [scaffolded_correct, answer=83] (17 words): मैडम… 3 लिखा, 1 हासिल ऊपर रखा… 3 और 4 और 1 जोड़े, 8 आया… तो 83।
- T3 teacher: 713 और जो अब गिनकर आया, इनमें कौन-सा सही है?
  - acts tagged: ['contrast_answers']  -> child state **CORRECT**
  - priya [correct_explained, answer=83] (17 words): मैडम… 3 लिखा, 1 हासिल ऊपर रखा। 3 और 4 और 1 जोड़े, 8 आया… तो 83।
- T4 teacher: अब अकेले करो: 56 और 29।
  - acts tagged: ['give_new_problem']  -> child state **CORRECT**
  - priya [correct_explained, answer=85] (17 words): दीदी… 5 लिखा, 1 हासिल ऊपर रखा। 5 और 2 और 1 जोड़े, 8 आया… तो 85।
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 1, 'checks_on_new_problem': 2}
  - strength: आपने «713 कैसे आया?» पूछकर प्रिया की उलझन सामने लाई और उत्तर खुद नहीं बताया।
  - change: दोनों संख्याएँ बंडल-तीली से बनवाइए, फिर खुली तीलियों का नया बंडल प्रिया से बँधवाइए और 'क्यों?' पूछिए।
  - exact words: खुली तीलियाँ मिलाओ, 10 का नया बंडल बाँधो। अब कितनी बचीं, और क्यों?

## Scene 6: NUM_ADD_CARRY_BUNDLES / aman

- diagnosis text: 'अमन ने हासिल गलत जगह जोड़ा, 3 को हासिल बना दिया' -> **correct** (keyword_match, matched=ADD_CARRY_WRONG_DIGIT, classifier=False)
- T1 teacher: अमन, 38 और 45 में तुमने पहले क्या जोड़ा?
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - aman [explain_bug, answer=101] (18 words): दीदी, 1 लिखा... 3 हासिल ऊपर रखा। 3 और 4 और 3 हासिल जोड़े, 10 आया... तो 101।
- T2 teacher: ये बंडल और तीलियाँ देखो। खुली तीलियाँ 13 हुईं, इनमें से 10 का बंडल बनाओ, कितनी बचीं?
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - aman [scaffolded_correct, answer=83] (18 words): दीदी, 3 लिखा... 1 हासिल ऊपर रखा। 3 और 4 और 1 हासिल जोड़े... 8 आया, तो 83।
- T3 teacher: तुमने 101 कहा था। अब गिनकर दूसरा उत्तर आया, कौन-सा सही है?
  - acts tagged: ['contrast_answers']  -> child state **CORRECT**
  - aman [correct_explained, answer=83] (18 words): दीदी, 3 लिखा... 1 हासिल ऊपर रखा। 3 और 4 और 1 हासिल जोड़े, 8 आया... तो 83।
- T4 teacher: शाबाश, अब खुद करो: 27 और 48।
  - acts tagged: ['praise_generic', 'give_new_problem']  -> child state **CORRECT**
  - aman [correct_explained, answer=75] (18 words): दीदी, 5 लिखा... 2 हासिल ऊपर रखा। 2 और 4 और 1 हासिल जोड़े, 7 आया... तो 75।
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 1, 'checks_on_new_problem': 2}
  - strength: आपने «कौन-सा सही है?» पूछकर उत्तर खुद नहीं बताया, अमन से दोनों उत्तरों की तुलना करवाई।
  - change: पहले अमन से 38 और 45 बंडल-तीली से बनवाइए, फिर 10 तीलियों का नया बंडल उसी से बँधवाइए।
  - exact words: अमन, पहले 38 और 45 बंडल-तीली से बनाओ, फिर बताओ यह नया बंडल क्यों बना?

## Scene 7: NUM_PLACE_VALUE_BUNDLES / ravi

- diagnosis text: 'रवि ने अंक उल्टे लिख दिए, पहले इकाई का अंक लिखा' -> **correct** (keyword_match, matched=PV_REVERSAL, classifier=False)
- T1 teacher: रवि, तुमने ये संख्या कैसे लिखी? पहले कौन-सा अंक लिखा?
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - ravi [explain_bug, answer=74] (9 words): दीदी, पहले 7 लिखा, फिर 4, तो 74 है!
- T2 teacher: सब मेरे साथ गिनो। हर बंडल में 10 तीलियाँ: 10, 20, 30, 40, फिर खुली तीलियाँ गिनो।
  - acts tagged: ['concrete_representation', 'model_step_aloud']  -> child state **PARTIAL**
  - ravi [scaffolded_correct, answer=47] (18 words): दीदी, नहीं नहीं! 4 बंडल में 40 तीलियाँ होती हैं, एक बंडल में 10। तो जवाब 47 है!
- T3 teacher: तुमने 74 कहा था और गिनकर कुछ और आया। कौन-सा सही है?
  - acts tagged: ['contrast_answers']  -> child state **CORRECT**
  - ravi [correct_explained, answer=47] (19 words): दीदी, एक बंडल में 10 तीलियाँ, तो 4 बंडल में 40। 40 और 7 मिलाओ, 47! यही सही है!
- T4 teacher: अब ये करो: 3 बंडल और 5 खुली तीलियाँ कितनी हुईं?
  - acts tagged: ['give_new_problem']  -> child state **CORRECT**
  - ravi [correct_explained, answer=35] (19 words): दीदी, एक बंडल में 10 तीलियाँ, तो 3 बंडल में 30। 30 और 5 मिलाओ, 35! यही सही है!
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 2, 'probes_with_followup': 2, 'checks_on_new_problem': 2}
  - strength: आपने पूछा «तुमने ये संख्या कैसे लिखी?», जिससे रवि की असली उलझन, उल्टे अंक लिखना, सामने आई।
  - change: अगली बार रवि से दहाई और इकाई के घर बनवाकर बंडल और खुली तीलियाँ अलग-अलग रखवाइए।
  - exact words: बंडल किस घर में रखोगे और खुली तीलियाँ किसमें? अंक भी उसी क्रम में लिखो।

## Scene 8: NUM_PLACE_VALUE_BUNDLES / priya

- diagnosis text: 'प्रिया हर बंडल को एक गिनती है, दस नहीं' -> **correct** (keyword_match, matched=PV_BUNDLE_AS_ONE, classifier=False)
- T1 teacher: प्रिया, तुमने कैसे गिना? धीरे से बताओ।
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - priya [explain_bug, answer=11] (9 words): मैडम… 4 बंडल और 7 तीलियाँ, सब गिनीं… 11
- T2 teacher: देखो, हर बंडल में कितनी तीलियाँ हैं? मेरे साथ गिनो: 10, 20, 30, 40।
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - priya [scaffolded_correct, answer=47] (15 words): दीदी… एक बंडल में 10 तीलियाँ, तो 4 बंडल में… 40… और 7… तो 47।
- T3 teacher: तुमने 11 कहा था, गिनने पर कितना आया? कौन-सा ठीक है?
  - acts tagged: ['repeat_question']  -> child state **PARTIAL**
  - priya [scaffolded_correct, answer=47] (14 words): दीदी… एक बंडल में 10… तो 4 बंडल में 40… और 7… तो… 47।
- T4 teacher: अब ये करो: 6 बंडल और 2 खुली तीलियाँ।
  - acts tagged: ['give_new_problem']  -> child state **PARTIAL**
  - priya [relapse, answer=8] (10 words): दीदी… 6 बंडल और 2 तीलियाँ, सब गिनीं… तो 8।
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'PARTIAL', 'PARTIAL']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 1, 'checks_on_new_problem': 1}
  - strength: आपने शुरू में «तुमने कैसे गिना? धीरे से बताओ।» पूछकर प्रिया की उलझन सामने ला दी।
  - change: प्रिया बंडल को 1 गिनती है; नए सवाल पर 8 आया, तो बंडल-तीलियाँ गिनवाकर पूछिए।
  - exact words: इस बार हर बंडल की तीलियाँ गिनकर दिखाओ, फिर खुली तीलियाँ। कितना आया?

## Scene 9: NUM_PLACE_VALUE_BUNDLES / aman

- diagnosis text: 'अमन चालीस सुनकर 40 लिखता है और उसके आगे 7 लिख देता है' -> **correct** (keyword_match, matched=PV_CONCAT_SPOKEN, classifier=False)
- T1 teacher: अमन, तुमने 407 कैसे लिखा? बताओ।
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - aman [explain_bug, answer=407] (17 words): दीदी, एक बंडल में 10 तीलियाँ, तो 4 बंडल में 40... 40 और 7, तो 407 लिखा।
- T2 teacher: आओ गिनते हैं: 4 बंडल यानी 10, 20, 30, 40, फिर 7 खुली तीलियाँ। मिलाकर कितनी हुईं?
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - aman [scaffolded_correct, answer=47] (17 words): दीदी, एक बंडल में 10 तीलियाँ... तो 4 बंडल में 40... और 40 और 7... तो 47।
- T3 teacher: तुमने 407 कहा, गिनकर कुछ और आया। कौन-सा सही है और क्यों?
  - acts tagged: ['contrast_answers']  -> child state **CORRECT**
  - aman [correct_explained, answer=47] (17 words): दीदी, एक बंडल में 10 तीलियाँ... तो 4 बंडल में 40... और 40 और 7 मिलाकर 47।
- T4 teacher: अब खुद करो: 3 बंडल और 5 तीलियाँ।
  - acts tagged: ['give_new_problem']  -> child state **CORRECT**
  - aman [correct_explained, answer=35] (17 words): दीदी, एक बंडल में 10 तीलियाँ... तो 3 बंडल में 30... और 30 और 5... तो 35।
- states by turn: ['CAN_EXPLAIN', 'PARTIAL', 'CORRECT', 'CORRECT']; turns: 4
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 2, 'uses_concrete_representation': 1, 'probes_with_followup': 2, 'checks_on_new_problem': 2}
  - strength: आपने «तुमने 407 कैसे लिखा? बताओ।» पूछकर अमन की सोच सामने लाई और उत्तर खुद नहीं बताया।
  - change: गिनती आप खुद न बोलें; अमन से हर बंडल की दस तीलियाँ, फिर खुली तीलियाँ गिनवाइए।
  - exact words: अमन, अब तुम तीलियाँ उठाकर गिनो: 10, 20, 30, 40, फिर खुली तीलियाँ।

## Scene 10: NUM_SUB_REGROUP_BUNDLES / ravi / tell-answer relapse

- diagnosis text: 'रवि ने छोटी संख्या में से बड़ी घटा दी' -> **correct** (classifier_match, matched=SUB_SMALLER_FROM_LARGER, classifier=True)
- T1 teacher: रवि, सही उत्तर 16 है, इसे याद कर लो।
  - acts tagged: ['tell_answer']  -> child state **MISCONCEPTION**
  - ravi [parrot, answer=16] (4 words): दीदी, सोलह! सोलह है!
- T2 teacher: रवि, तुमने कैसे किया?
  - acts tagged: ['ask_to_explain']  -> child state **CAN_EXPLAIN**
  - ravi [explain_bug, answer=24] (19 words): दीदी, तो 7 में से 3 घटाया, 4 आया। 4 में से 2 घटाया, 2 आया। तो 24 है!
- T3 teacher: बंडल खोलकर गिनो, कितनी खुली तीलियाँ हुईं?
  - acts tagged: ['concrete_representation']  -> child state **PARTIAL**
  - ravi [scaffolded_correct, answer=16] (20 words): दीदी, 13 में से 7 घटाया, 6 आया। 3 में से 2 घटाया, 1 आया। तो सोलह! सोलह ही है!
- T4 teacher: अब नया सवाल: 61 में से 28।
  - acts tagged: ['give_new_problem']  -> child state **PARTIAL**
  - ravi [relapse, answer=47] (19 words): दीदी, तो 8 में से 1 घटाया, 7 आया। 6 में से 2 घटाया, 4 आया। तो 47 है!
- T5 teacher: और ये भी करो: 74 में से 39।
  - acts tagged: ['give_new_problem']  -> child state **PARTIAL**
  - ravi [relapse, answer=45] (19 words): दीदी, तो 9 में से 4 घटाया, 5 आया। 7 में से 3 घटाया, 4 आया। तो 45 है!
- states by turn: ['MISCONCEPTION', 'CAN_EXPLAIN', 'PARTIAL', 'PARTIAL', 'PARTIAL']; turns: 5
- coach (fallback_used=False): scores={'asks_to_explain': 2, 'does_not_tell_answer': 0, 'uses_concrete_representation': 1, 'probes_with_followup': 0, 'checks_on_new_problem': 1}
  - strength: आपने «तुमने कैसे किया?» पूछकर रवि का 7 में से 3 घटाने वाला तरीका सामने ला दिया।
  - change: शुरू में उत्तर न बताइए; रवि के दो उत्तर, 24 और 16, सामने रखकर उसी से तुलना करवाइए।
  - exact words: तुम्हारे दो उत्तर आए, 24 और 16। कौन-सा सही है, और क्यों?
