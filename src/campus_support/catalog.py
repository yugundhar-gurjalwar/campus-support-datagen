"""Static, synthetic content: categories, policy fact catalog, text templates, name pools.
Nothing here is sourced from an external dataset (see metadata/source_manifest.json)."""
from __future__ import annotations

# fact tuple: (key, requester question, policy sentence with {v}, unit, value choices)
# category tuple: (id, domain, domain_name, name, default_priority, human_review,
#                  deadline_sensitive, sampling weight, description, facts)
CATEGORIES = [
    ("CAT-FIN-01", "FIN", "financial_aid", "Aid status and disbursement", "normal", False, False, 8.0,
     "Questions about award status, disbursement timing and refunds of excess aid.", [
        ("disbursement_lag_days", "When will my financial aid be disbursed to my account?",
         "Financial aid is disbursed {v} days after the term census date.", "days", [7, 10, 14, 21]),
        ("min_credit_hours", "How many credit hours do I need for my aid to be paid?",
         "Aid requires enrollment in at least {v} credit hours.", "credits", [3, 6, 9, 12]),
        ("refund_payout_days", "How long until an aid refund reaches my bank?",
         "Excess-aid refunds are issued within {v} business days.", "business days", [3, 5, 7, 10])]),
    ("CAT-FIN-02", "FIN", "financial_aid", "Verification documents", "normal", False, True, 6.0,
     "Verification requests, document uploads and review timelines.", [
        ("verification_deadline_days", "How long do I have to submit my verification documents?",
         "Verification documents are due within {v} days of the request notice.", "days", [14, 21, 30, 45]),
        ("doc_review_days", "How long does review of my submitted documents take?",
         "Submitted documents are reviewed within {v} business days.", "business days", [5, 7, 10, 15]),
        ("tax_transcript_requirement", "Do I need to upload a tax transcript?",
         "A tax transcript is {v} for dependent applicants.", "", ["required", "optional"])]),
    ("CAT-FIN-03", "FIN", "financial_aid", "Satisfactory progress appeal", "normal", True, False, 2.0,
     "Appeals after losing aid eligibility for academic progress; requires human decision.", [
        ("sap_min_gpa", "What GPA do I need to keep my financial aid?",
         "Minimum cumulative GPA for aid eligibility is {v}.", "GPA", [2.0, 2.25, 2.5]),
        ("sap_appeal_window_days", "How long do I have to file a progress appeal?",
         "Progress appeals must be filed within {v} days of the notice.", "days", [10, 14, 21, 30]),
        ("completion_rate_pct", "What course completion rate do I need?",
         "Students must complete at least {v} percent of attempted credits.", "percent", [67, 70, 75])]),
    ("CAT-FIN-04", "FIN", "financial_aid", "Tuition payment and refunds", "normal", False, True, 7.0,
     "Payment plans, due dates, late fees and tuition refunds.", [
        ("payment_due_days", "When is my tuition payment due?",
         "Tuition is due {v} days before the term start date.", "days", [7, 10, 14, 21]),
        ("late_fee_pct", "What is the late payment fee?",
         "A late fee of {v} percent applies to overdue balances.", "percent", [1.5, 2.0, 3.0, 5.0]),
        ("refund_pct_week2", "How much tuition is refunded if I drop in week two?",
         "Withdrawal during week two earns a {v} percent tuition refund.", "percent", [50, 60, 75, 80])]),
    ("CAT-REG-01", "REG", "registration", "Add, drop and withdraw", "normal", False, True, 9.0,
     "Course add/drop windows, withdrawal deadlines and fees.", [
        ("add_deadline_day", "What is the last day to add a course?",
         "Courses may be added through day {v} of the term.", "term day", [5, 7, 10, 14]),
        ("withdraw_deadline_day", "When is the last day to withdraw with a W grade?",
         "Withdrawal with a W grade is allowed through day {v} of the term.", "term day", [40, 45, 50, 60]),
        ("drop_fee_usd", "Is there a fee to drop a course?",
         "A course drop after the add deadline incurs a fee of {v} USD.", "USD", [0, 25, 50, 75])]),
    ("CAT-REG-02", "REG", "registration", "Holds and prerequisites", "normal", False, False, 6.0,
     "Registration holds, prerequisite overrides and credit-load limits.", [
        ("hold_clear_days", "How long does it take to clear a registration hold?",
         "Registration holds are cleared within {v} business days of resolution.", "business days", [1, 2, 3, 5]),
        ("prereq_override_approver", "Who can approve a prerequisite override?",
         "Prerequisite overrides must be approved by the {v}.", "",
         ["department chair", "course instructor", "academic advisor"]),
        ("max_credit_load", "What is the maximum credit load per term?",
         "The standard maximum load is {v} credits per term.", "credits", [15, 16, 18, 19])]),
    ("CAT-REG-03", "REG", "registration", "Transcripts and records", "low", False, False, 5.0,
     "Official transcripts, enrollment verification and records requests.", [
        ("transcript_processing_days", "How long do official transcripts take to process?",
         "Official transcripts are processed within {v} business days.", "business days", [1, 2, 3, 5]),
        ("transcript_fee_usd", "How much does an official transcript cost?",
         "Each official transcript costs {v} USD.", "USD", [0, 5, 8, 10]),
        ("enrollment_letter_days", "How fast can I get an enrollment verification letter?",
         "Enrollment verification letters are issued within {v} business days.", "business days", [1, 2, 3])]),
    ("CAT-REG-04", "REG", "registration", "Grade change and roster correction", "normal", True, False, 2.5,
     "Grade change petitions and roster corrections; requires human approval.", [
        ("grade_change_window_days", "How long after the term can a grade change be filed?",
         "Grade changes must be filed within {v} days after the term ends.", "days", [30, 45, 60, 90]),
        ("grade_change_approver", "Who must approve a grade change?",
         "Grade changes require approval from the {v}.", "",
         ["department chair", "dean of the college", "registrar"]),
        ("roster_correction_days", "How long do roster corrections take?",
         "Roster corrections are applied within {v} business days.", "business days", [2, 3, 5])]),
    ("CAT-IT-01", "IT", "it", "Account, password and MFA", "normal", False, False, 12.0,
     "Sign-in problems, password resets and multi-factor authentication.", [
        ("password_expiry_days", "How often do I have to change my password?",
         "Passwords expire every {v} days.", "days", [90, 180, 365]),
        ("lockout_minutes", "How long is my account locked after failed sign-ins?",
         "Accounts lock for {v} minutes after five failed sign-ins.", "minutes", [15, 30, 60]),
        ("mfa_method", "Which multi-factor method does the campus support?",
         "The supported multi-factor method is {v}.", "", ["authenticator app", "hardware key", "sms code"])]),
    ("CAT-IT-02", "IT", "it", "LMS and course access", "normal", False, False, 8.0,
     "Course shells, enrollment sync and learning-platform access.", [
        ("lms_enroll_sync_hours", "When will my course show up in the learning platform?",
         "Courses appear in the learning platform within {v} hours of enrollment.", "hours", [2, 4, 12, 24]),
        ("course_shell_open_days", "How early do course shells open?",
         "Instructor course shells open {v} days before the term starts.", "days", [7, 10, 14]),
        ("lms_storage_gb", "How much file storage does each course get?",
         "Each course shell includes {v} GB of file storage.", "GB", [5, 10, 20])]),
    ("CAT-IT-03", "IT", "it", "Wi-Fi and software licenses", "low", False, False, 6.0,
     "Campus Wi-Fi registration, VPN and licensed software.", [
        ("wifi_device_limit", "How many devices can I register on campus Wi-Fi?",
         "Each user may register up to {v} devices.", "devices", [3, 5, 8]),
        ("software_license_days", "How long do student software licenses last?",
         "Licensed software is activated for {v} days per grant.", "days", [180, 365]),
        ("vpn_requirement", "Do I need the VPN for library databases off campus?",
         "VPN use is {v} for off-campus library databases.", "", ["required", "optional"])]),
    ("CAT-IT-04", "IT", "it", "Security incident", "high", True, False, 1.5,
     "Compromised accounts and phishing; requires human security review.", [
        ("incident_report_hours", "How quickly must I report a compromised account?",
         "Suspected compromises must be reported within {v} hours.", "hours", [4, 12, 24, 48]),
        ("account_freeze_hours", "How long will my account be frozen during review?",
         "Compromised accounts are frozen for up to {v} hours during review.", "hours", [24, 48, 72]),
        ("phishing_report_channel", "Where do I report a phishing message?",
         "Phishing messages are reported through the {v}.", "",
         ["security portal", "help desk phone line", "report-phish button"])]),
    ("CAT-ACC-01", "ACC", "accessibility", "Accommodation intake information", "normal", False, False, 3.0,
     "How to start an accommodation request and what documentation is needed.", [
        ("intake_ack_days", "How soon will I hear back after submitting an intake request?",
         "Intake requests are acknowledged within {v} business days.", "business days", [2, 3, 5]),
        ("documentation_age_years", "How recent does my supporting documentation need to be?",
         "Supporting documentation must be dated within {v} years.", "years", [3, 5]),
        ("intake_meeting_days", "How soon will my intake meeting be scheduled?",
         "Intake meetings are scheduled within {v} days of the request.", "days", [7, 10, 14])]),
    ("CAT-ACC-02", "ACC", "accessibility", "Accommodation determination", "high", True, False, 2.0,
     "Decisions, appeals and interim measures for accommodation requests; requires human decision.", [
        ("determination_days", "How long does an accommodation decision take?",
         "Accommodation determinations are issued within {v} business days.", "business days", [10, 15, 20]),
        ("determination_appeal_days", "How long do I have to appeal a decision?",
         "Determination appeals must be filed within {v} days.", "days", [14, 21, 30]),
        ("interim_accommodation_days", "Can I get interim accommodations while I wait?",
         "Interim accommodations apply for up to {v} days pending a decision.", "days", [10, 15, 30])]),
    ("CAT-ACC-03", "ACC", "accessibility", "Assistive technology", "normal", False, False, 3.0,
     "Assistive technology loans, captioning and alternative formats.", [
        ("at_loan_days", "How long can I borrow assistive technology?",
         "Assistive technology may be loaned for {v} days per term.", "days", [30, 60, 90]),
        ("at_request_lead_days", "How far ahead should I request assistive technology?",
         "Assistive technology requests need {v} days of lead time.", "days", [5, 7, 10]),
        ("captioning_lead_days", "How much notice does live captioning need?",
         "Live captioning requires {v} days of notice.", "days", [3, 5, 7])]),
    ("CAT-ACC-04", "ACC", "accessibility", "Exam accommodation logistics", "high", False, True, 4.0,
     "Booking accommodated exams and testing-centre logistics.", [
        ("exam_request_days", "How far ahead must I book an accommodated exam?",
         "Accommodated exams must be booked {v} days before the exam date.", "days", [3, 5, 7]),
        ("extended_time_pct", "How much extended exam time do I get?",
         "Standard extended time is {v} percent of the regular exam length.", "percent", [50, 100]),
        ("testing_center_close", "How late is the testing centre open?",
         "The testing centre is open until {v} on weekdays.", "", ["17:00", "18:00", "20:00"])]),
]

DOMAIN_TEAM = {"FIN": "TEAM-FIN", "REG": "TEAM-REG", "IT": "TEAM-IT", "ACC": "TEAM-ACC"}
TEAM_DEFS = [  # id, name, tier, domain, calendar, escalation team
    ("TEAM-FIN", "Financial Aid Office", 1, "FIN", "CAL-STD", "TEAM-ACADADM"),
    ("TEAM-REG", "Registrar's Office", 1, "REG", "CAL-STD", "TEAM-ACADADM"),
    ("TEAM-IT", "IT Help Desk", 1, "IT", "CAL-EXT", "TEAM-PLATFORM"),
    ("TEAM-ACC", "Accessibility Services", 1, "ACC", "CAL-STD", "TEAM-ACADADM"),
    ("TEAM-ACADADM", "Academic Administration Office", 2, "ADMIN", "CAL-STD", None),
    ("TEAM-PLATFORM", "Platform Administration", 2, "PLAT", "CAL-EXT", None),
]
TEAM_DEPT = {"TEAM-FIN": "FAO", "TEAM-REG": "REGO", "TEAM-IT": "ITS", "TEAM-ACC": "DSS",
             "TEAM-ACADADM": "ADM", "TEAM-PLATFORM": "ITS"}
ROLE_DEFS = [
    ("ROLE-LEARNER", "Learner", "requester", True, False, "Student making support requests."),
    ("ROLE-INSTRUCTOR", "Instructor", "requester", True, False, "Faculty member making support requests."),
    ("ROLE-ACADADMIN", "Academic Administrator", "admin", True, True,
     "Files requests and, when attached to the tier-2 team, decides escalated cases."),
    ("ROLE-SUPPORT", "Support Staff", "staff", False, True, "Tier-1 desk agent."),
    ("ROLE-PLATADMIN", "Platform Administrator", "admin", False, True, "Tier-2 platform/security handler."),
]
SLA_DEFS = [("SLAP-URGENT", "urgent", 60, 480), ("SLAP-HIGH", "high", 240, 1440),
            ("SLAP-NORMAL", "normal", 480, 2400), ("SLAP-LOW", "low", 960, 4800)]
TERM_DEFS = [  # id, name, start, end, registration opens
    ("TERM-2025-FA", "Fall 2025", (2025, 8, 25), (2025, 12, 12), (2025, 4, 7)),
    ("TERM-2026-SP", "Spring 2026", (2026, 1, 12), (2026, 5, 8), (2025, 10, 20)),
    ("TERM-2026-SU", "Summer 2026", (2026, 5, 18), (2026, 8, 7), (2026, 3, 2)),
    ("TERM-2026-FA", "Fall 2026", (2026, 8, 24), (2026, 12, 11), (2026, 4, 6)),
]
ROLE_MIX_BY_DOMAIN = {  # (learner, instructor, academic admin requester)
    "FIN": (0.97, 0.01, 0.02), "REG": (0.80, 0.17, 0.03),
    "IT": (0.65, 0.32, 0.03), "ACC": (0.80, 0.18, 0.02)}
VARIANTS = ["Standard Procedure", "Deadlines and Exceptions", "Eligibility Criteria",
            "Fees and Timelines", "Special Circumstances"]

# ---------------------------------------------------------------- text templates
Q_CLEAR = ["Hi, {q}", "Hello, quick question: {q}", "I need to know: {q}", "Could you tell me? {q}",
           "{q} Thanks in advance.", "Hi team, {q} I could not find it on the website."]
Q_MODERATE = ["I have a question about {topic} but I am not sure what applies to my situation.",
              "I am confused about {topic}. Can someone explain how it works for me?",
              "Something about {topic} does not look right on my record, what should I do?"]
Q_VAGUE = ["Something is wrong and I need help, please advise.", "It is about my case. Please call me.",
           "I have a problem, I do not know who to ask.", "Need help with the thing we discussed last term."]
SUBJ_VAGUE = ["Help needed", "Please advise", "Issue with my case", "Need assistance", "Question"]
DEADLINE_TAILS = ["I need this sorted before {when}.", "My deadline is {when}, so this is time sensitive.",
                  "This is urgent because of a deadline on {when}."]
CLARIFY_REQ = ["Thanks for reaching out. So I can point you to the right policy, which topic is this about: {topics}?",
               "To make sure I give you the correct information, could you tell me exactly what you need: {topics}?",
               "Could you clarify your question? Is it related to {topics}?"]
CLARIFY_OK = ["It is about {topic}. Specifically: {q}", "Sorry for the confusion, my question is about {topic}. {q}"]
CLARIFY_VAGUE = ["I am not sure, it is complicated and I cannot explain it better.",
                 "It is just not working and I do not know the details.", "Like I said, I need help with my case."]
ANSWER_INTRO = ["Hello,", "Thanks for your patience.", "Good news, I found the relevant policy.", "Hi,"]
ACK = ["Thanks for your message. We are reviewing your request and will update you by the next business day.",
       "We have picked up your case and are checking the details now.",
       "Quick update: your request is in progress, no action needed from you yet."]
FOLLOWUP = ["Any update on this?", "Just checking in, I have not heard back yet.",
            "Could someone look at this today? Thanks.", "Following up on my request."]
THANKS = ["Thanks, that resolves it.", "Perfect, thank you for the quick help.", "Got it, thanks."]
REOPEN = ["This did not fully answer my question, can you recheck?",
          "I tried that and it still does not work. Please reopen.",
          "The deadline you mentioned seems different from what my advisor told me."]
SYSTEM_ACK = ["Your request {tid} was received and routed to the {team}. Keep this reference for follow-ups."]
ESC_TEXT = {
    "human_review_required": "this request type needs a documented human decision",
    "no_current_policy": "no current policy version covers this question",
    "ambiguity_unresolved": "the question is still unclear after two clarification attempts",
    "urgent_deadline": "your deadline is within 24 hours and needs expedited handling",
}
HANDOFF = ["After specialist review: {decision}", "Decision from the {team}: {decision}",
           "We reviewed your case in detail. {decision}"]
DECISIONS = ["we have approved the request and updated your record.",
             "we cannot approve this request as submitted; the policy terms apply.",
             "we have granted a one-time exception and recorded it on your file.",
             "we have completed the review and the outcome is posted to your portal."]

FIRST = ["Aiden", "Priya", "Mateo", "Sofia", "Noah", "Amara", "Liam", "Mei", "Omar", "Hannah", "Ravi", "Elena",
         "Kofi", "Yuki", "Lucas", "Zara", "Diego", "Anika", "Ethan", "Fatima", "Jonas", "Nia", "Arjun", "Clara",
         "Tariq", "Isla", "Mohan", "Leila", "Owen", "Sana", "Felix", "Ingrid", "Hugo", "Layla", "Dev", "Maya"]
LAST = ["Alvarez", "Banerjee", "Chen", "Dubois", "Eriksen", "Fofana", "Garcia", "Haddad", "Ivanov", "Jensen",
        "Khan", "Lopez", "Mbeki", "Novak", "Okafor", "Patel", "Quinn", "Rossi", "Sato", "Tanaka", "Umar",
        "Vargas", "Weber", "Xu", "Yilmaz", "Zhou", "Adeyemi", "Bauer", "Costa", "Das", "Evans", "Fischer"]
DEPTS = ["CS", "BUS", "NUR", "ENG", "ART", "BIO"]
