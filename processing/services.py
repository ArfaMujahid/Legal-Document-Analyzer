import pdfplumber
import pytesseract
from PIL import Image
import io
import logging
import os
import re
from docx import Document as DocxDocument
from django.conf import settings
from .models import ProcessingLog

logger = logging.getLogger(__name__)

class TextExtractor:
    """Extract text from various document formats"""

    @staticmethod
    def extract_from_pdf(file_path):
        """Extract text from PDF using pdfplumber"""
        text = ""
        needs_ocr = False

        try:
            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                logger.info(f"Processing PDF with {total_pages} pages")

                for page_num, page in enumerate(pdf.pages):
                    try:
                        page_text = page.extract_text()
                        if page_text:
                            text += page_text + "\n"
                            logger.debug(f"Extracted text from page {page_num + 1}/{total_pages}")
                        else:
                            # Page might be scanned, need OCR
                            needs_ocr = True
                            logger.debug(f"Page {page_num + 1} appears to be scanned, may need OCR")
                    except Exception as page_error:
                        logger.warning(f"Failed to extract text from page {page_num + 1}: {page_error}")
                        continue

            logger.info(f"PDF extraction completed, extracted {len(text)} characters")

            if needs_ocr or not text.strip():
                logger.info("Attempting OCR as no text was extracted or pages appear scanned")
                ocr_text = TextExtractor._ocr_pdf(file_path)
                # Keep the text layer unless OCR recovered more (e.g. one blank page
                # must not discard a whole digital PDF when Tesseract is missing).
                if len(ocr_text.strip()) > len(text.strip()):
                    text = ocr_text

        except Exception as e:
            logger.error(f"PDF extraction failed: {str(e)}")
            ProcessingLog.log_error('text_extraction', f"PDF extraction failed: {str(e)}")
            return None

        # Clean up text by removing Content-ID references
        import re
        text = re.sub(r'\(cid:\d+\)', '', text)
        return text.strip()

    @staticmethod
    def extract_from_docx(file_path):
        """Extract text from DOCX file"""
        try:
            doc = DocxDocument(file_path)
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            return text.strip()
        except Exception as e:
            ProcessingLog.log_error('text_extraction', f"DOCX extraction failed: {str(e)}")
            return None

        # Clean up text by removing Content-ID references
        import re
        text = re.sub(r'\(cid:\d+\)', '', text)
        return text.strip()

    @staticmethod
    def extract_from_txt(file_path):
        """Extract text from TXT file"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except UnicodeDecodeError:
            # Try with different encoding
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    return f.read().strip()
            except Exception as e:
                ProcessingLog.log_error('text_extraction', f"TXT extraction failed: {str(e)}")
                return None
        except Exception as e:
            ProcessingLog.log_error('text_extraction', f"TXT extraction failed: {str(e)}")
            return None

    @staticmethod
    def _ocr_pdf(file_path):
        """Perform OCR on PDF using Tesseract"""
        try:
            # Convert PDF to images and OCR each page
            import fitz  # PyMuPDF
            text = ""

            doc = fitz.open(file_path)
            for page_num in range(len(doc)):
                page = doc.load_page(page_num)
                pix = page.get_pixmap()
                img_data = pix.tobytes("png")
                img = Image.open(io.BytesIO(img_data))

                # Perform OCR
                page_text = pytesseract.image_to_string(img)
                text += page_text + "\n"

            doc.close()

            # Clean up text by removing Content-ID references
            import re
            text = re.sub(r'\(cid:\d+\)', '', text)
            return text.strip()
        except ImportError:
            ProcessingLog.log_error('ocr', "PyMuPDF not installed for OCR")
            return ""
        except Exception as e:
            ProcessingLog.log_error('ocr', f"OCR failed: {str(e)}")
            return ""


class MetadataExtractor:
    """Extract metadata from document text"""

    @staticmethod
    def extract_title(text, filename):
        """Extract document title"""
        # Try to find title in first few lines
        lines = text.split('\n')[:10]

        # Look for patterns that might be titles
        for line in lines:
            line = line.strip()
            if len(line) > 10 and len(line) < 100:
                # Check if it's capitalized (possible title)
                if line[0].isupper() and not line.endswith('.'):
                    return line

        # Fallback to filename without extension
        return os.path.splitext(filename)[0]

    @staticmethod
    def extract_dates(text):
        """Extract dates from text"""
        date_patterns = [
            r'\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b',  # MM/DD/YYYY or MM-DD-YYYY
            r'\b\d{4}[/-]\d{1,2}[/-]\d{1,2}\b',    # YYYY/MM/DD or YYYY-MM-DD
            r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}\b',
            r'\b\d{1,2}\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b'
        ]

        dates = []
        for pattern in date_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            dates.extend(matches)

        return dates[:5]  # Return first 5 dates found

    @staticmethod
    def extract_parties(text):
        """Extract party names from legal documents"""
        # Common patterns for party identification
        party_patterns = [
            r'between\s+([A-Z][a-z]+\s+(?:[A-Z][a-z]*\s*)?[A-Z][a-z]+)\s+and',
            r'BY\s+AND\s+BETWEEN\s+([A-Z][a-z\s]+)\s+\(',
            r'PARTIES:\s*([A-Z][a-z\s]+)\s+\(',
            r'Client:\s*([A-Z][a-z\s]+)',
            r'Contractor:\s*([A-Z][a-z\s]+)',
        ]

        parties = []
        for pattern in party_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            parties.extend(matches)

        # Clean up and deduplicate
        cleaned_parties = []
        for party in parties:
            party = party.strip().title()
            if len(party) > 3 and party not in cleaned_parties:
                cleaned_parties.append(party)

        return cleaned_parties[:5]  # Return first 5 parties


class TextChunker:
    """Split text into chunks with overlap"""

    def __init__(self, chunk_size=1000, overlap=200):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk_text(self, text):
        """Split text into chunks with sentence-aware boundaries"""
        if not text:
            return []

        # First, split text into sentences
        sentences = self._split_into_sentences(text)

        chunks = []
        current_chunk = []
        current_length = 0
        chunk_start = 0

        for i, sentence in enumerate(sentences):
            sentence_length = len(sentence)

            # If adding this sentence would exceed chunk size and we have content
            if current_length + sentence_length > self.chunk_size and current_chunk:
                # Create chunk from current sentences
                chunk_text = ' '.join(current_chunk).strip()
                chunk_end = chunk_start + len(chunk_text)

                # Only add if chunk is substantial
                if len(chunk_text) > 50:  # Minimum chunk size
                    chunks.append({
                        'text': chunk_text,
                        'start_offset': chunk_start,
                        'end_offset': chunk_end
                    })

                # Start new chunk with overlap
                overlap_sentences = []
                overlap_length = 0

                # Add sentences from the end for overlap
                for j in range(len(current_chunk) - 1, -1, -1):
                    s = current_chunk[j]
                    if overlap_length + len(s) <= self.overlap:
                        overlap_sentences.insert(0, s)
                        overlap_length += len(s)
                    else:
                        break

                current_chunk = overlap_sentences + [sentence]
                current_length = overlap_length + sentence_length
                chunk_start = chunk_end - overlap_length
            else:
                # Add sentence to current chunk
                current_chunk.append(sentence)
                current_length += sentence_length

        # Add the last chunk if it has content
        if current_chunk and current_length > 50:
            chunk_text = ' '.join(current_chunk).strip()
            chunks.append({
                'text': chunk_text,
                'start_offset': chunk_start,
                'end_offset': chunk_start + len(chunk_text)
            })

        return chunks

    def _split_into_sentences(self, text):
        """Split text into sentences using multiple delimiters"""
        import re

        # Clean up text first - preserve line breaks for better sentence detection
        text = re.sub(r'\s+', ' ', text)  # Normalize multiple spaces
        text = re.sub(r'\n+', '\n', text)  # Normalize line breaks

        # Simple approach: split on common sentence endings followed by whitespace or newlines
        # This is more reliable than complex regex patterns
        sentences = []
        lines = text.split('\n')

        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Split on sentence endings
            parts = re.split(r'([.!?])\s+', line)

            # Reconstruct sentences
            current_sentence = ""
            for i in range(0, len(parts), 2):
                if i < len(parts):
                    sentence_part = parts[i].strip()
                    if sentence_part:
                        # Re-insert the space re.split consumed ("9." + "LIMITATION")
                        if current_sentence:
                            current_sentence += ' '
                        current_sentence += sentence_part

                    # Add punctuation if available
                    if i + 1 < len(parts):
                        current_sentence += parts[i + 1]

                        # If this looks like a complete sentence, add it
                        if len(current_sentence) > 20 and current_sentence[-1] in '.!?':
                            sentences.append(current_sentence)
                            current_sentence = ""

            # Add any remaining text
            if current_sentence.strip():
                if not current_sentence.endswith(('.', '!', '?')):
                    current_sentence += '.'
                sentences.append(current_sentence)

        return sentences

    def _find_sentence_boundary(self, text, search_length):
        """Find the best sentence boundary within search_length"""
        if search_length >= len(text):
            search_length = len(text) - 1

        # Search from the end backwards
        for i in range(search_length, 0, -1):
            if text[i] in '.!?':
                # Found sentence ending
                return i + 1

        return 0  # No sentence boundary found


class SectionExtractor:
    """Extract document sections using heuristics"""

    @staticmethod
    def extract_sections(text):
        """Extract sections from document text"""
        sections = []

        # Patterns for section headings
        heading_patterns = [
            r'^(\d+\.\s+.*$)',  # Numbered headings: "1. Introduction"
            r'^([A-Z][A-Z\s]+:?$)',  # All caps headings: "TERMS AND CONDITIONS"
            r'^([IVX]+\.\s+.*$)',  # Roman numerals: "I. INTRODUCTION"
            r'^([A-Z]\.\s+.*$)',  # Letter headings: "A. Definitions"
            r'^(Article\s+\d+\..*$)',  # Article headings: "Article 1. Definitions"
            r'^(Section\s+\d+\..*$)',  # Section headings: "Section 1. Definitions"
        ]

        lines = text.split('\n')
        current_section = None
        section_start = 0

        for i, line in enumerate(lines):
            line = line.strip()

            # Check if this line is a heading
            for pattern in heading_patterns:
                match = re.match(pattern, line, re.MULTILINE)
                if match:
                    # Save previous section
                    if current_section:
                        current_section['end_offset'] = sum(len(l) + 1 for l in lines[:i])
                        sections.append(current_section)

                    # Start new section
                    current_section = {
                        'title': line,
                        'label': match.group(1),
                        'start_offset': sum(len(l) + 1 for l in lines[:i]),
                        'confidence': 0.8
                    }
                    section_start = i
                    break

        # Don't forget the last section
        if current_section:
            current_section['end_offset'] = len(text)
            sections.append(current_section)

        return sections