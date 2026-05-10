"""
Demo transcripts for new users to test workflows without connecting Fireflies.

Each transcript matches the Fireflies webhook `transcript` field format.
"""

from fastapi import APIRouter, Depends
from auth import get_current_active_user
import models

router = APIRouter()

DEMO_TRANSCRIPTS = [
    {
        "id": "demo_discovery",
        "title": "Discovery Call — CloudStack Solutions",
        "meeting_title": "Discovery — CloudStack Solutions",
        "duration": 14,
        "participants": ["Sarah Chen", "Mark Thompson"],
        "participant_emails": ["sarah@example.com", "mark@example.com"],
        "organizer_email": "sarah@example.com",
        "recipient_email": "mark@example.com",
        "type": "Discovery Call",
        "transcript": """Sarah Chen: Hey Mark, thanks for hopping on. I know you're busy so I appreciate you making the time.
Mark Thompson: No worries at all. I've been meaning to look into this for a while actually.
Sarah Chen: Oh nice, so what prompted you to book the call?
Mark Thompson: Honestly, we've been scaling the sales team pretty aggressively. We went from four reps to eleven in the last six months.
Sarah Chen: Wow, that's serious growth.
Mark Thompson: Yeah it is. And the problem is our follow-up process completely broke when we scaled.
Mark Thompson: Like when it was four people I could just check in with everyone, make sure deals were moving. Now it's chaos.
Sarah Chen: Yeah, that's super common at that stage. So tell me a bit about what your current process looks like.
Mark Thompson: Sure. So we use Pipedrive for our CRM.
Sarah Chen: Oh great, we integrate directly with Pipedrive.
Mark Thompson: Good, good. So we've got Pipedrive and we use Fireflies to record all our sales meetings.
Mark Thompson: The problem is there's this massive gap between the meeting happening and the follow-up actually going out.
Sarah Chen: How long are we talking?
Mark Thompson: Sometimes two, three days. Sometimes it just doesn't happen at all.
Mark Thompson: I pulled the numbers last month and roughly thirty percent of our meetings had zero follow-up within the first week.
Sarah Chen: Thirty percent, that's a lot of potential revenue just sitting there.
Mark Thompson: Exactly. And the reps aren't lazy or anything. They're just overwhelmed.
Mark Thompson: They come out of a meeting, they've got three more back to back, and by the time they sit down to write follow-up emails they can barely remember what was discussed.
Sarah Chen: Right, so the context is gone.
Mark Thompson: The context is completely gone. They end up sending these generic templates that don't reference anything specific from the conversation.
Mark Thompson: And I know our prospects can tell because our reply rates have been dropping.
Sarah Chen: What are your reply rates looking like right now?
Mark Thompson: On follow-up sequences, we're hovering around eight to ten percent.
Sarah Chen: Okay. And when your reps do send personalized follow-ups that actually reference the meeting, what do those reply rates look like?
Mark Thompson: Oh, way better. Probably twenty-five, thirty percent. But that takes them like twenty, thirty minutes per email to write.
Sarah Chen: Yeah, that math doesn't work at scale.
Mark Thompson: It really doesn't. So that's why I'm here. I need something that bridges that gap.
Sarah Chen: Makes total sense. So let me ask, when your reps finish a meeting right now, what happens next in terms of workflow?
Mark Thompson: So Fireflies records the meeting, generates a transcript and a summary.
Mark Thompson: The rep is supposed to update the deal in Pipedrive, log the meeting notes, and then draft a follow-up sequence.
Sarah Chen: And realistically, how much of that actually happens?
Mark Thompson: Pipedrive gets updated maybe sixty percent of the time. Meeting notes, maybe forty. Follow-up sequences, like I said, maybe seventy percent and most of those are templated.
Sarah Chen: Got it. So there's basically a three-part problem. The CRM isn't getting updated consistently, the meeting intelligence is going to waste, and the follow-ups are either late, generic, or missing entirely.
Mark Thompson: Yeah, that's a pretty accurate summary.
Sarah Chen: And how are you handling sequences right now? Are you using any outreach tool?
Mark Thompson: We've looked at a few. We tried Salesloft briefly but it was overkill for what we needed and the price point was insane.
Mark Thompson: Right now reps are just sending emails manually from Gmail or using basic Pipedrive email templates.
Sarah Chen: And those templates, who creates them?
Mark Thompson: I do, mostly. We've got maybe fifteen templates for different scenarios.
Mark Thompson: But they're static. They don't adapt to what was actually discussed in the meeting.
Sarah Chen: Right. So the rep has to manually customize each one.
Mark Thompson: Which brings us back to the time problem. They either send it generic or they don't send it at all.
Sarah Chen: Totally. So if I'm hearing you right, the dream scenario would be something where the meeting ends, and a personalized multi-touch sequence just appears, ready to go, without the rep having to think about it.
Mark Thompson: That would be incredible. Is that actually what you do?
Sarah Chen: That's exactly what we do. We pull the transcript from Fireflies, extract the key context, pain points, action items, and we generate a full email sequence that's personalized to that specific conversation.
Mark Thompson: And it syncs with Pipedrive?
Sarah Chen: Directly. The sequences show up in the deal record, contacts get updated, and the rep can review and launch the sequence with one click.
Mark Thompson: How long does that take from meeting end to sequence ready?
Sarah Chen: Usually under two minutes.
Mark Thompson: And the emails actually sound good? Like they reference specific things we talked about?
Sarah Chen: They reference specific pain points, commitments, next steps. Everything that came up in the conversation gets woven into the sequence naturally.
Mark Thompson: Okay, that's interesting. What does pricing look like?
Sarah Chen: It depends on the plan and how many sequences you're running. Happy to walk you through the tiers after I understand a bit more about your volume.
Sarah Chen: How many meetings is your team running per week roughly?
Mark Thompson: Across eleven reps, probably sixty to seventy meetings a week.
Sarah Chen: Okay, cool. And are all of those being recorded in Fireflies?
Mark Thompson: Most of them. Probably eighty-five, ninety percent.
Sarah Chen: Great. That gives me a good picture. Would it be helpful if I set up a proper demo so you can see exactly how the transcript-to-sequence flow works?
Mark Thompson: Yeah, I think that would be the logical next step.
Sarah Chen: Perfect. I can also show you some before and after examples of reply rates from teams similar to yours.
Mark Thompson: That'd be great. Can we do it sometime next week?
Sarah Chen: Absolutely. How's Tuesday afternoon?
Mark Thompson: Tuesday works. Let's say two o'clock Eastern?
Sarah Chen: Done. I'll send a calendar invite after this. Is there anyone else from your team who should be on that demo?
Mark Thompson: Yeah, probably our sales manager, Karen. She's the one who'd be rolling this out to the reps.
Sarah Chen: Perfect. If you can forward her the invite, I'll make sure to tailor the demo to what managers need to see as well.
Mark Thompson: Will do.
Sarah Chen: Awesome. Just to recap, Tuesday at two, I'll show you the full flow from transcript to sequence, Pipedrive integration, and some case study data. Sound good?
Mark Thompson: Sounds great. Looking forward to it.
Sarah Chen: Same here. Thanks so much for the time today, Mark.
Mark Thompson: Thank you, Sarah. Talk Tuesday.
Sarah Chen: Talk Tuesday. Bye.
Mark Thompson: Bye.""",
    },
    {
        "id": "demo_sales_demo",
        "title": "Sales Demo — BrightPath Consulting",
        "meeting_title": "Demo — BrightPath Consulting",
        "duration": 16,
        "participants": ["Rachel Kim", "David Martinez", "Lisa Park"],
        "participant_emails": ["rachel@example.com", "david@example.com", "lisa@example.com"],
        "organizer_email": "rachel@example.com",
        "recipient_email": "david@example.com",
        "type": "Sales Demo",
        "transcript": """Rachel Kim: Hey David, hey Lisa. Can you guys hear me okay?
David Martinez: Yep, we're good.
Lisa Park: Hi Rachel, good to see you again.
Rachel Kim: You too. So David, I know Lisa sat in on the intro call last week, but just to catch you up quickly, Lisa mentioned that your team's main bottleneck is the gap between meeting recordings and getting sequences out the door. Sound right?
David Martinez: Yeah, Lisa filled me in. I've been dealing with this problem for years honestly.
David Martinez: We run about forty consulting discovery calls a week across six consultants and the follow-up is always the weak link.
Rachel Kim: Got it. So what I want to show you today is exactly how a meeting transcript turns into a ready-to-send email sequence. I've actually loaded up a sample transcript that's similar to a consulting discovery call so it should feel pretty realistic.
David Martinez: Oh nice, that's helpful.
Rachel Kim: Cool. So let me share my screen.
Rachel Kim: Okay, so you can see here, this is the dashboard. When a meeting ends and the transcript comes in from Fireflies, it shows up right here in the pipeline.
Lisa Park: Oh, I like that it shows the deal stage next to it. That's pulling from Pipedrive?
Rachel Kim: Exactly. It pulls the deal context from Pipedrive automatically so the AI knows where this prospect is in the pipeline when it generates the sequence.
David Martinez: Smart. So it's not just looking at the transcript in isolation.
Rachel Kim: Right. The deal stage, the contact history, any notes already in Pipedrive, it all feeds into the sequence generation.
Rachel Kim: So let me click into this one. You can see the transcript summary here at the top. Key pain points extracted, action items, and then down here is the generated sequence.
David Martinez: How many emails is that?
Rachel Kim: This one generated four touches over ten days. But the number of touches and the cadence depends on the plan and the complexity of the conversation.
Rachel Kim: So first email goes out same day, references the specific challenges discussed. Second email two days later with a relevant resource. Third is a soft check-in. Fourth is a clear call to action for next steps.
Lisa Park: Can I see the actual email copy?
Rachel Kim: Of course. So here's the first email. You can see it opens by referencing the prospect's specific situation, their team scaling from twelve to twenty-five people and the onboarding bottleneck they mentioned.
David Martinez: Okay, that's actually impressive. That's not generic at all.
Rachel Kim: And that's the whole point. Every email in the sequence is built from what was actually said in the meeting. Not a template with a name swapped in.
Lisa Park: What if the rep wants to tweak something before it sends?
Rachel Kim: Great question. Everything is editable. The rep can modify any email, adjust timing, add or remove a touch. Nothing sends without approval.
David Martinez: That's important. I don't want my team blindly blasting AI-generated emails.
Rachel Kim: Totally agree. Human review is always in the loop.
David Martinez: Okay, what about the Pipedrive side? Walk me through that.
Rachel Kim: Sure. So when the sequence is approved, the activity gets logged in the deal record automatically. Each email send, each open, each reply, it all flows back into Pipedrive.
Rachel Kim: So your sales manager view in Pipedrive stays accurate without anyone having to manually log anything.
Lisa Park: That alone would save us hours. I spend like an hour a day just making sure reps have updated their deals.
Rachel Kim: Yeah, we hear that a lot.
David Martinez: What about email deliverability? Are these sending from our domain?
Rachel Kim: Yes. Emails send from your team's actual email accounts via OAuth. Gmail or Outlook. So it looks exactly like the rep sat down and wrote the email themselves.
David Martinez: Good. What about the AI cost? Is there a limit on how many sequences we can generate?
Rachel Kim: So we use a credit system called Acorns. Each plan comes with a monthly allocation and different sequence types use different amounts depending on complexity.
Rachel Kim: For your volume of about forty meetings a week across six people, the Oak plan would cover you comfortably.
David Martinez: And what does Oak run?
Rachel Kim: Ninety-nine dollars per user per month. Or seventy-nine on annual billing.
David Martinez: Per user. So six users would be.
Rachel Kim: Five ninety-four monthly, or four seventy-four on annual.
David Martinez: That's actually pretty reasonable considering what Salesloft quoted us.
Lisa Park: It was like three times that, and we'd still have to write the sequences ourselves.
Rachel Kim: Yeah, that's the key difference. You're not paying for a sequence builder where you still have to do the work. The sequences come to you already built from the meeting context.
David Martinez: What's the setup process like? How long until we're actually running?
Rachel Kim: Most teams are live within an hour. You connect Pipedrive, connect Fireflies, authorize your email accounts, and you're set. Next meeting that gets recorded, a sequence appears.
David Martinez: An hour. Really.
Rachel Kim: Yeah, it's all OAuth connections. No engineering work, no data migration.
Lisa Park: What about the free plan? Could we test with one or two people first?
Rachel Kim: Absolutely. The free tier gives you a hundred Acorns per month which is enough to generate a handful of sequences and see the quality.
Rachel Kim: A lot of teams start one or two people on free, validate the output quality, then roll out to the full team.
David Martinez: That seems smart. Lisa, what do you think?
Lisa Park: I think we should get two of our highest-volume consultants on the free plan this week and see what comes out of their next calls.
David Martinez: Agreed. Rachel, can we get set up today?
Rachel Kim: I can send you the signup link right after this call. Takes about ten minutes to connect everything.
David Martinez: Perfect.
Rachel Kim: And I'll include a quick start guide that walks through the first sequence review so your consultants know what to expect.
Lisa Park: That would be great.
Rachel Kim: Awesome. Any other questions before we wrap?
David Martinez: One more. If we like what we see and want to roll out to all six people, is there a volume discount?
Rachel Kim: The annual billing discount is the main one, but I can also have our team put together a custom quote if you're looking at six plus seats.
David Martinez: Let's see how the pilot goes first and then we'll talk numbers.
Rachel Kim: Sounds perfect. I'll get you that signup link within the hour.
David Martinez: Great. Thanks Rachel, this was really helpful.
Lisa Park: Yeah, super helpful. Thanks Rachel.
Rachel Kim: Thank you both. Excited to see what your team thinks of the sequences. Talk soon.
David Martinez: Talk soon. Bye.
Lisa Park: Bye.
Rachel Kim: Bye.""",
    },
    {
        "id": "demo_client_review",
        "title": "Monthly Review — Apex Digital",
        "meeting_title": "Monthly Review — Apex Digital",
        "duration": 15,
        "participants": ["James Wilson", "Emma Roberts"],
        "participant_emails": ["james@example.com", "emma@example.com"],
        "organizer_email": "james@example.com",
        "recipient_email": "emma@example.com",
        "type": "Client Check-in",
        "transcript": """James Wilson: Hey Emma, how's it going?
Emma Roberts: Hey James, good. Busy as always but good busy.
James Wilson: Good busy is the best kind. So I pulled up your numbers for the month. Want to dive right in?
Emma Roberts: Yeah, let's do it.
James Wilson: Cool. So across your eight reps, you generated a hundred and forty-two sequences this month, which is up from a hundred and eighteen last month.
Emma Roberts: Makes sense, we had a big push on outbound this month.
James Wilson: And the results are showing. Your average reply rate on generated sequences is sitting at twenty-three percent.
Emma Roberts: How does that compare to what you see across other teams?
James Wilson: Industry average for cold follow-up sequences is around eight to twelve percent. For meeting-based follow-ups like yours, we typically see teams landing between eighteen and twenty-five. So you're right in the sweet spot.
Emma Roberts: Nice. That's a huge improvement from where we were. Before we started using you guys we were at like nine percent.
James Wilson: Yeah, that's more than double. And your team's using the personalization well. I noticed they're actually reviewing and tweaking the sequences before sending, which is great.
Emma Roberts: Yeah, I was firm about that. I told them it's a tool to help, not a replacement for thinking.
James Wilson: Smart approach. So one thing I wanted to flag. I noticed about fifteen percent of your sequences are getting generated from pretty thin transcripts. Like meetings under five minutes or calls where the audio quality was rough.
Emma Roberts: Yeah, we've had some connection issues with a few of the Zoom calls. Is that affecting the sequence quality?
James Wilson: It can. When the transcript is thin, the AI has less context to work with so the personalization isn't as strong.
James Wilson: What I'd recommend is when the system flags a thin transcript, have the rep add a quick note about what was discussed. Just two or three bullet points. The AI will incorporate that and the output quality jumps significantly.
Emma Roberts: That's easy enough. I'll add that to our process doc.
James Wilson: Great. The other thing I wanted to touch on is Acorn usage.
Emma Roberts: Yeah, I was going to ask about that actually.
James Wilson: So you're on the Oak plan, three hundred and seventy-five Acorns per user per month. Across eight users that's three thousand total.
James Wilson: You burned through twenty-eight hundred this month, which is healthy but you're trending upward with the volume increase.
Emma Roberts: So if we keep ramping, we might hit the ceiling.
James Wilson: Possibly. You've got a couple options. You can grab a top-up pack if you go over in a given month, or if this volume is the new normal, it might make sense to look at the Redwood plan for your highest-volume reps.
Emma Roberts: What's the difference with Redwood again?
James Wilson: Eight hundred Acorns per month per user, more advanced sequence options, priority generation, and API access for your dev team if you want to build custom workflows.
Emma Roberts: What's the price jump?
James Wilson: Two forty-nine per user per month. Or one ninety-nine on annual.
Emma Roberts: So it would only make sense for our heavy hitters. Not everyone.
James Wilson: Exactly. You could mix and match. Keep most of the team on Oak and bump your top two or three reps to Redwood.
Emma Roberts: That's smart. Let me look at who's burning through the most Acorns and I'll get back to you.
James Wilson: I can actually pull that report for you right now. Give me one second.
James Wilson: Okay so your top three by usage are Marcus Chen at four hundred and twelve, Priya Patel at three eighty-nine, and Tom Nguyen at three sixty-one.
Emma Roberts: Yeah, those are my closers. They run twice as many meetings as everyone else.
James Wilson: So if you bumped those three to Redwood you'd have way more headroom and the rest of the team stays on Oak comfortably.
Emma Roberts: Makes sense. Can I do that mid-cycle or do I need to wait?
James Wilson: You can upgrade anytime. It prorates for the rest of the billing period.
Emma Roberts: Okay, let me think about it this week. Probably going to do it though.
James Wilson: No rush. Just flag me when you're ready and I'll handle it.
Emma Roberts: Will do. Anything else on your end?
James Wilson: One more thing. We're rolling out a new feature next month that I think you'll love.
James Wilson: Basically before your rep's next meeting with a contact, the system will surface a summary of everything discussed in previous meetings. Past pain points, commitments, status of action items, all pulled from the transcript history.
Emma Roberts: Oh, that's huge. So they'd walk into the meeting already knowing exactly where things left off?
James Wilson: Exactly. No more scrambling to review notes five minutes before the call.
Emma Roberts: When is that available?
James Wilson: Should be live in about four weeks. I'll make sure your team gets early access.
Emma Roberts: Amazing. That alone is going to save us so much prep time.
James Wilson: That's the goal. So to summarize, reply rates looking strong, watch for thin transcripts and have reps add context notes, keep an eye on Acorn usage for your top reps, and meeting prep panel coming soon.
Emma Roberts: Got it. Clear and actionable. I appreciate it, James.
James Wilson: Of course. Same time next month?
Emma Roberts: Actually, can we move it to the second week? I've got a board presentation the first week of next month.
James Wilson: Absolutely. I'll send an updated invite for the second Tuesday.
Emma Roberts: Perfect. Thanks James.
James Wilson: Thank you, Emma. Great month. Keep it up.
Emma Roberts: Will do. Talk soon.
James Wilson: Talk soon. Bye.
Emma Roberts: Bye.""",
    },
]


@router.get("/demo-transcripts")
async def get_demo_transcripts(
    _current_user: models.User = Depends(get_current_active_user),
):
    """Return demo transcripts for testing workflows."""
    return [
        {
            "id": t["id"],
            "title": t["title"],
            "type": t["type"],
            "duration": t["duration"],
            "participants": t["participants"],
        }
        for t in DEMO_TRANSCRIPTS
    ]


@router.get("/demo-transcripts/{transcript_id}")
async def get_demo_transcript(
    transcript_id: str,
    _current_user: models.User = Depends(get_current_active_user),
):
    """Return a specific demo transcript with full data."""
    for t in DEMO_TRANSCRIPTS:
        if t["id"] == transcript_id:
            return t
    from fastapi import HTTPException
    raise HTTPException(status_code=404, detail="Demo transcript not found")
