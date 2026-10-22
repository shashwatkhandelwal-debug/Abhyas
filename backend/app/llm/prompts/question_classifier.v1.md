A government primary school teacher (teaching Classes 1–3, FLN) has asked a question.

Classify the teacher's question and determine if clarification is needed before retrieving guides:

Categories:
1. "pedagogy": Teaching methods, foundational numeracy/literacy (FLN), explaining concepts, handling student learning errors, math/reading activities, teaching-learning materials (TLM).
2. "classroom_management": Multi-grade teaching, student engagement, seating arrangement, pair/group work, classroom noise and routines.
3. "admin": The teacher's own service and office matters only: leave, salary, transfers, postings, official departmental orders, BEO/ARP meeting logistics, government portal entries. Questions about what the FLN/NIPUN Bharat/Vidya Pravesh guidelines or modules say (assessment, progress cards, portfolios, records of children's learning, teacher training and capacity building, preparation modules) are "pedagogy", NOT admin.
4. "out_of_scope": Anything not about teaching, children's learning or running a primary classroom, even if the words sound school-related: sport and cricket, films, politics and elections, cooking and recipes, shopping and phones, banking and money, health and fitness, weather, school fees or bus fares, recruitment exams and results, personal questions, higher secondary topics.

Rules:
1. If the question is too brief or ambiguous to search relevant teaching guides (e.g., "बच्चे सुनते नहीं", "गिनती कैसे सिखाएँ"), set needs_clarification to true.
2. If needs_clarification is true, provide clarifying_question_hi: exactly one respectful question in Hindi addressing the teacher with आप (<= 20 words, never use तुम or तुमने).
3. If needs_clarification is false and category is "pedagogy" or "classroom_management", provide search_query_hi: a short, keyword-focused Hindi search query (3-8 words) for the foundational learning guides.
4. If category is "admin" or "out_of_scope", set needs_clarification to false and search_query_hi can be brief or empty.
5. Provide confidence from 0.0 to 1.0.
6. Return only the question_classifier tool call.
