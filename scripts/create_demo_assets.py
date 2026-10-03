"""Rebuild original, captioned teaching fixtures. Requires ffmpeg and Pillow."""
import json
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.util import Inches, Pt
from pptx.oxml.xmlchemy import OxmlElement
from reportlab.pdfgen import canvas

DEST = Path(__file__).resolve().parents[1] / "backend/labtwin/demo_assets"
PASSAGES = [
    ("Linked Lists", "A linked list stores nodes connected by next pointers. The head pointer identifies the first node. An empty list has a null head."),
    ("Insertion at the beginning", "To insert at the beginning of a linked list, first connect the new node to the previous head. Then update the head pointer to the new node. This preserves the existing chain."),
    ("The conceptual mistake", "If the new node's next pointer is set to NULL before updating the head, the old nodes become unreachable. The first insertion can pass while insertion into a non-empty list fails."),
    ("Reassessment: count the nodes", "To count the nodes, start at head, increment the count once for each visited node, and follow next until NULL. An empty list has zero nodes."),
]


def create():
    DEST.mkdir(parents=True, exist_ok=True)
    pdf = canvas.Canvas(str(DEST / "Data-Structures-Notes.pdf"))
    import textwrap
    for number, (title, paragraph) in enumerate(PASSAGES, 1):
        pdf.setFont("Helvetica-Bold", 20); pdf.drawString(45, 770, title)
        pdf.setFont("Helvetica", 13)
        for index, line in enumerate(textwrap.wrap(paragraph, 75)):
            pdf.drawString(45, 720 - index * 24, line)
        if number == 2:
            labels = ["head", "new node", "previous head", "NULL"]
            pdf.setFont("Helvetica", 11)
            for index, label in enumerate(labels):
                x = 45 + index * 130
                pdf.rect(x, 510, 110, 55)
                pdf.drawString(x + 8, 534, label)
                if index < 3:
                    pdf.line(x + 110, 537, x + 130, 537)
                    arrow = pdf.beginPath(); arrow.moveTo(x + 130, 537); arrow.lineTo(x + 123, 541); arrow.lineTo(x + 123, 533); arrow.close()
                    pdf.drawPath(arrow, fill=1)
            pdf.drawString(45, 475, "Figure 1: connect new node to previous head, then head to new node.")
        pdf.drawString(45, 60, f"LabTwin demo teaching material | Page {number}")
        pdf.showPage()
    pdf.save()
    slides = Presentation()
    for number, (title, paragraph) in enumerate(PASSAGES, 1):
        slide = slides.slides.add_slide(slides.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = paragraph
        if number == 2:
            slide.placeholders[1].height = Inches(2)
            boxes = []
            for index, label in enumerate(["head", "new node", "previous head", "NULL"]):
                box = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(.3 + index * 2.45), Inches(4), Inches(2.1), Inches(.8))
                box.text = label
                box.text_frame.paragraphs[0].font.size = Pt(18)
                boxes.append(box)
            for left, right in zip(boxes, boxes[1:]):
                edge = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, left.left + left.width, left.top + left.height // 2, right.left, right.top + right.height // 2)
                edge.begin_connect(left, 3); edge.end_connect(right, 1)
                arrow = OxmlElement("a:tailEnd"); arrow.set("type", "triangle"); edge._element.spPr.get_or_add_ln().append(arrow)
    slides.save(DEST / "Linked-Lists.pptx")
    captions = [{"start": index * 10, "end": (index + 1) * 10, "text": f"{title}. {paragraph}"} for index, (title, paragraph) in enumerate(PASSAGES)]
    (DEST / "Lecture-4.captions.json").write_text(json.dumps(captions, indent=2))
    with tempfile.TemporaryDirectory() as temp:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        title_font, body_font = ImageFont.truetype(font_path, 40), ImageFont.truetype(font_path, 25)
        for index, (title, paragraph) in enumerate(PASSAGES):
            frame = Image.new("RGB", (1280, 720), "#f5faf9")
            draw = ImageDraw.Draw(frame)
            draw.rectangle((0, 0, 1280, 100), fill="#063e37")
            draw.text((60, 28), "LABTWIN  /  DATA STRUCTURES", font=body_font, fill="white")
            draw.text((60, 160), title, font=title_font, fill="#073e37")
            for line_index, line in enumerate(textwrap.wrap(paragraph, 75)):
                draw.text((60, 250 + line_index * 45), line, font=body_font, fill="#243a36")
            draw.text((60, 630), f"Lecture 4  |  Chapter {index + 1}  |  Captioned demo lecture", font=body_font, fill="#33796c")
            frame.save(Path(temp) / f"frame{index:02d}.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-framerate", "1/10", "-i", str(Path(temp) / "frame%02d.png"), "-f", "lavfi", "-i", "anullsrc=channel_layout=mono:sample_rate=16000", "-t", "40", "-c:v", "libx264", "-r", "10", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(DEST / "Lecture-4.mp4")], check=True)
        vtt = Path(temp) / "lecture.vtt"
        vtt.write_text("WEBVTT\n\n" + "\n\n".join(f"00:00:{row['start']:02d}.000 --> 00:00:{row['end']:02d}.000\n{row['text']}" for row in captions))
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(DEST / "Lecture-4.mp4"), "-i", str(vtt), "-map", "0:v", "-map", "0:a", "-map", "1:0", "-c:v", "libvpx-vp9", "-crf", "35", "-b:v", "0", "-c:a", "libopus", "-c:s", "webvtt", str(DEST / "Lecture-4.webm")], check=True)


if __name__ == "__main__":
    create()
