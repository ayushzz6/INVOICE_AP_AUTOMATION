from __future__ import annotations

import base64
import os
import tempfile
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable

import pandas as pd
import streamlit as st

from models import db
from pipeline.orchestrator import process_invoice

SAMPLE_PDF_DIR = Path("data/sample_invoices")
INBOX_PDF_DIR = Path("data/inbox")

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass

st.set_page_config(page_title="Zamp AP Automation", page_icon="Z", layout="wide", initial_sidebar_state="expanded")


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --zamp-bg: #f6f8fb;
            --zamp-surface: #ffffff;
            --zamp-surface-soft: #f8fafc;
            --zamp-border: #e6eaf0;
            --zamp-border-strong: #d8dee8;
            --zamp-text: #111827;
            --zamp-muted: #6b7280;
            --zamp-blue: #1f5eff;
            --zamp-blue-dark: #1746c7;
            --zamp-teal: #047c74;
            --zamp-green: #15803d;
            --zamp-amber: #b45309;
            --zamp-red: #be123c;
            --zamp-shadow: 0 18px 45px rgba(17, 24, 39, 0.07);
            --zamp-shadow-soft: 0 8px 24px rgba(17, 24, 39, 0.05);
        }
        #MainMenu, header, footer, [data-testid="stToolbar"], [data-testid="stDecoration"] {
            display: none !important;
        }
        .stApp {
            background:
                radial-gradient(circle at 12% -8%, rgba(31, 94, 255, 0.10), transparent 28rem),
                radial-gradient(circle at 90% 0%, rgba(4, 124, 116, 0.07), transparent 24rem),
                linear-gradient(180deg, #ffffff 0%, var(--zamp-bg) 42%, #f2f5f9 100%);
            color: var(--zamp-text);
        }
        .main .block-container {
            padding: 28px 46px 48px;
            max-width: 1220px;
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--zamp-border);
            box-shadow: 8px 0 28px rgba(17, 24, 39, 0.04);
            min-width: 250px;
        }
        [data-testid="stSidebar"] * {
            color: var(--zamp-text);
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h2 {
            font-size: 1.05rem;
            margin-bottom: 0;
        }
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p {
            color: var(--zamp-muted);
            font-size: 0.78rem;
        }
        [data-testid="stSidebar"] [role="radiogroup"] {
            gap: 6px;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] {
            background: transparent;
            border: 1px solid transparent;
            border-radius: 12px;
            padding: 9px 10px;
            margin: 2px 0;
            transition: all 0.16s ease;
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"]:hover {
            background: #f5f7fb;
            border-color: var(--zamp-border);
        }
        [data-testid="stSidebar"] label[data-baseweb="radio"] > div:first-child {
            transform: scale(0.78);
        }
        [data-testid="stMetric"] {
            background: var(--zamp-surface);
            border: 1px solid var(--zamp-border);
            border-radius: 18px;
            padding: 18px 18px 15px;
            box-shadow: var(--zamp-shadow-soft);
        }
        [data-testid="stMetricLabel"] {
            color: var(--zamp-muted);
        }
        [data-testid="stMetricValue"] {
            color: var(--zamp-text);
        }
        h1, h2, h3, h4, h5, h6, p, label, span {
            color: var(--zamp-text);
            font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        }
        .topbar {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 4px 0 20px;
        }
        .brand-lockup {
            display: flex;
            align-items: center;
            gap: 12px;
            font-weight: 800;
            letter-spacing: -0.02em;
        }
        .brand-mark {
            width: 34px;
            height: 34px;
            border-radius: 10px;
            background: linear-gradient(135deg, var(--zamp-blue), var(--zamp-teal));
            color: #ffffff;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            font-weight: 900;
        }
        .topbar-meta {
            color: var(--zamp-muted);
            font-size: 0.82rem;
            border: 1px solid var(--zamp-border);
            background: #ffffff;
            padding: 8px 12px;
            border-radius: 999px;
        }
        .sidebar-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 8px 2px 18px;
            margin-bottom: 10px;
        }
        .sidebar-brand-name {
            font-weight: 850;
            letter-spacing: -0.03em;
            line-height: 1.1;
        }
        .sidebar-brand-sub {
            color: var(--zamp-muted);
            font-size: 0.72rem;
            margin-top: 2px;
        }
        .sidebar-footer {
            border: 1px solid var(--zamp-border);
            background: #f8fafc;
            border-radius: 14px;
            padding: 12px;
            font-size: 0.76rem;
            color: var(--zamp-muted);
            margin-top: 18px;
        }
        .hero {
            border: 1px solid var(--zamp-border);
            border-radius: 24px;
            padding: 30px 32px;
            background:
                linear-gradient(135deg, rgba(31, 94, 255, 0.07), rgba(4, 124, 116, 0.045)),
                var(--zamp-surface);
            box-shadow: var(--zamp-shadow);
            margin-bottom: 24px;
            position: relative;
            overflow: hidden;
        }
        .hero:after {
            content: "";
            position: absolute;
            width: 220px;
            height: 220px;
            right: -70px;
            top: -90px;
            background: radial-gradient(circle, rgba(31, 94, 255, 0.10), transparent 70%);
        }
        .eyebrow {
            color: var(--zamp-blue);
            text-transform: uppercase;
            letter-spacing: 0.16em;
            font-size: 0.72rem;
            font-weight: 800;
            margin-bottom: 10px;
        }
        .hero h1 {
            margin: 0;
            font-size: 2.25rem;
            line-height: 1.08;
            color: var(--zamp-text);
            letter-spacing: -0.03em;
            max-width: 720px;
        }
        .hero p {
            color: var(--zamp-muted);
            font-size: 1rem;
            max-width: 760px;
            margin: 12px 0 0;
        }
        .panel {
            border: 1px solid var(--zamp-border);
            border-radius: 22px;
            padding: 24px;
            background: var(--zamp-surface);
            box-shadow: var(--zamp-shadow-soft);
            margin-bottom: 20px;
        }
        .panel h3 {
            margin-top: 0;
            letter-spacing: -0.01em;
            font-size: 1.08rem;
        }
        .upload-panel {
            min-height: 228px;
        }
        .upload-panel p {
            max-width: 560px;
        }
        .workflow-animation {
            position: relative;
            min-height: 390px;
            border-radius: 24px;
            overflow: hidden;
            background:
                radial-gradient(circle at 50% 0%, rgba(31, 94, 255, 0.10), transparent 15rem),
                linear-gradient(180deg, #ffffff 0%, #f7faff 100%);
        }
        .workflow-animation:before {
            content: "";
            position: absolute;
            inset: 18px;
            border-radius: 22px;
            border: 1px solid rgba(31, 94, 255, 0.08);
            background-image:
                linear-gradient(rgba(31, 94, 255, 0.055) 1px, transparent 1px),
                linear-gradient(90deg, rgba(31, 94, 255, 0.055) 1px, transparent 1px);
            background-size: 26px 26px;
        }
        .flow-node {
            position: absolute;
            width: 132px;
            min-height: 74px;
            border: 1px solid #dbe6f5;
            border-radius: 18px;
            background: rgba(255, 255, 255, 0.92);
            box-shadow: 0 18px 40px rgba(31, 94, 255, 0.10);
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 8px;
            z-index: 2;
        }
        .flow-node span:first-child {
            width: 28px;
            height: 28px;
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            background: #eff6ff;
            color: var(--zamp-blue);
            font-weight: 900;
            font-size: 0.88rem;
        }
        .flow-node span:last-child {
            font-size: 0.74rem;
            font-weight: 800;
            color: #334155;
            letter-spacing: 0.02em;
            text-transform: uppercase;
        }
        .node-invoice { left: 7%; top: 42%; }
        .node-extract { left: 35%; top: 18%; }
        .node-controls { right: 9%; top: 42%; }
        .node-decision { left: 35%; bottom: 13%; }
        .flow-line {
            position: absolute;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(31, 94, 255, 0.35), transparent);
            z-index: 1;
            transform-origin: left center;
        }
        .line-a { width: 178px; left: 26%; top: 44%; transform: rotate(-26deg); }
        .line-b { width: 178px; left: 57%; top: 34%; transform: rotate(28deg); }
        .line-c { width: 186px; left: 56%; top: 63%; transform: rotate(151deg); }
        .line-d { width: 178px; left: 26%; top: 61%; transform: rotate(26deg); }
        .pulse-dot {
            position: absolute;
            width: 10px;
            height: 10px;
            border-radius: 999px;
            background: var(--zamp-blue);
            box-shadow: 0 0 0 7px rgba(31, 94, 255, 0.13);
            z-index: 3;
            animation: orbit 5.2s infinite ease-in-out;
        }
        .pulse-dot.two {
            animation-delay: 1.7s;
            background: var(--zamp-teal);
            box-shadow: 0 0 0 7px rgba(4, 124, 116, 0.12);
        }
        .pulse-dot.three {
            animation-delay: 3.4s;
            background: #64748b;
            box-shadow: 0 0 0 7px rgba(100, 116, 139, 0.12);
        }
        @keyframes orbit {
            0% { left: 18%; top: 50%; opacity: 0; transform: scale(0.8); }
            10% { opacity: 1; }
            30% { left: 44%; top: 28%; }
            52% { left: 72%; top: 50%; }
            74% { left: 44%; top: 72%; }
            92% { opacity: 1; }
            100% { left: 18%; top: 50%; opacity: 0; transform: scale(1); }
        }
        .decision-orb {
            position: absolute;
            inset: auto 0 28px 0;
            margin: auto;
            width: 190px;
            height: 36px;
            border-radius: 999px;
            background: linear-gradient(135deg, var(--zamp-blue), var(--zamp-teal));
            color: white;
            font-weight: 850;
            font-size: 0.78rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 18px 36px rgba(31, 94, 255, 0.22);
            animation: glow 2.6s infinite ease-in-out;
            z-index: 4;
        }
        @keyframes glow {
            0%, 100% { transform: translateY(0); filter: saturate(1); }
            50% { transform: translateY(-4px); filter: saturate(1.25); }
        }
        .decision-card {
            border-radius: 22px;
            padding: 24px;
            border: 1px solid var(--zamp-border);
            box-shadow: var(--zamp-shadow-soft);
            margin: 14px 0 20px;
        }
        .decision-approved { background: linear-gradient(135deg, #f0fdf4, #ffffff); border-left: 5px solid var(--zamp-green); }
        .decision-flagged { background: linear-gradient(135deg, #fffbeb, #ffffff); border-left: 5px solid var(--zamp-amber); }
        .decision-rejected { background: linear-gradient(135deg, #fff1f2, #ffffff); border-left: 5px solid var(--zamp-red); }
        .pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 6px 11px;
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.07em;
            text-transform: uppercase;
        }
        .pill-approved { background: #dcfce7; color: var(--zamp-green); }
        .pill-flagged { background: #fef3c7; color: var(--zamp-amber); }
        .pill-rejected { background: #ffe4e6; color: var(--zamp-red); }
        .decision-title {
            font-size: 1.25rem;
            font-weight: 800;
            margin: 16px 0 8px;
            color: var(--zamp-text);
        }
        .decision-copy {
            color: #334155;
            font-size: 1rem;
            line-height: 1.6;
            margin-bottom: 0;
        }
        .stage-row {
            border-left: 2px solid #dbe4ef;
            padding: 2px 0 16px 16px;
            margin-left: 6px;
            position: relative;
        }
        .stage-row:before {
            content: "";
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: var(--zamp-blue);
            position: absolute;
            left: -5px;
            top: 8px;
        }
        .stage-name {
            font-weight: 800;
            color: var(--zamp-text);
        }
        .stage-detail {
            color: var(--zamp-muted);
            font-size: 0.9rem;
        }
        .field-table {
            width: 100%;
            border-collapse: separate;
            border-spacing: 0;
            background: #ffffff;
            border: 1px solid var(--zamp-border);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: var(--zamp-shadow-soft);
            margin-bottom: 18px;
        }
        .field-table th {
            background: #f8fafc;
            color: #475569;
            font-size: 0.74rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
            text-align: left;
            padding: 12px 14px;
            border-bottom: 1px solid var(--zamp-border);
        }
        .field-table td {
            color: var(--zamp-text);
            padding: 13px 14px;
            border-bottom: 1px solid #eef2f7;
            font-size: 0.92rem;
            vertical-align: top;
        }
        .field-table tr:last-child td {
            border-bottom: 0;
        }
        .section-label {
            font-weight: 850;
            letter-spacing: -0.02em;
            margin: 12px 0 10px;
            color: var(--zamp-text);
        }
        .status-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 9px;
            background: #eff6ff;
            color: #1d4ed8;
            font-weight: 700;
            font-size: 0.78rem;
        }
        .subtle {
            color: var(--zamp-muted);
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--zamp-border);
            border-radius: 16px;
            overflow: hidden;
            box-shadow: var(--zamp-shadow-soft);
        }
        [data-testid="stFileUploader"] {
            margin-top: -8px;
        }
        [data-testid="stFileUploader"] section {
            background: #f8fbff !important;
            border: 1.5px dashed #b8c7dc !important;
            border-radius: 18px !important;
            min-height: 128px;
            transition: all 0.16s ease;
        }
        [data-testid="stFileUploader"] section:hover {
            border-color: var(--zamp-blue) !important;
            background: #f4f8ff !important;
        }
        [data-testid="stFileUploader"] small {
            color: var(--zamp-muted) !important;
        }
        [data-testid="stFileUploader"] button {
            background: #ffffff !important;
            color: var(--zamp-blue) !important;
            border: 1px solid var(--zamp-border-strong) !important;
            border-radius: 10px !important;
        }
        [data-testid="stStatusWidget"] {
            display: none;
        }
        .stButton > button {
            border-radius: 13px;
            border: 1px solid var(--zamp-border-strong) !important;
            background: #ffffff !important;
            color: var(--zamp-text) !important;
            box-shadow: none;
            font-weight: 800;
            min-height: 44px;
        }
        .stButton > button * {
            color: var(--zamp-text) !important;
        }
        .stButton > button[kind="primary"] {
            background: linear-gradient(135deg, var(--zamp-blue), var(--zamp-blue-dark)) !important;
            border-color: var(--zamp-blue) !important;
            color: #ffffff !important;
        }
        .stButton > button[kind="primary"] * {
            color: #ffffff !important;
        }
        .stButton > button:hover {
            border-color: var(--zamp-blue-dark);
            background: #f8fbff !important;
            transform: translateY(-1px);
        }
        .stButton > button[kind="primary"]:hover {
            background: linear-gradient(135deg, var(--zamp-blue-dark), var(--zamp-blue)) !important;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 8px;
        }
        .stTabs [data-baseweb="tab"] {
            border-radius: 999px;
            padding: 8px 16px;
            background: #ffffff;
            border: 1px solid var(--zamp-border);
            color: var(--zamp-text);
        }
        .stTabs [aria-selected="true"] {
            background: #eff6ff;
            border-color: #bfdbfe;
            color: var(--zamp-blue);
        }
        .stStatus {
            background: #ffffff !important;
            border: 1px solid var(--zamp-border) !important;
            color: var(--zamp-text) !important;
        }
        [data-testid="stStatus"] {
            background: #ffffff !important;
            border: 1px solid var(--zamp-border) !important;
        }
        [data-testid="stStatus"] * {
            color: var(--zamp-text) !important;
        }
        .readiness-card {
            border: 1px solid var(--zamp-border);
            background: #ffffff;
            border-radius: 22px;
            padding: 22px 24px;
            box-shadow: var(--zamp-shadow-soft);
            margin-bottom: 18px;
        }
        .readiness-head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 16px;
            margin-bottom: 14px;
        }
        .readiness-score {
            font-size: 2rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            color: var(--zamp-text);
        }
        .readiness-bar {
            height: 10px;
            border-radius: 999px;
            background: #eef2f7;
            overflow: hidden;
            margin: 10px 0 16px;
        }
        .readiness-fill {
            height: 100%;
            background: linear-gradient(90deg, var(--zamp-blue), var(--zamp-teal));
            border-radius: 999px;
        }
        .readiness-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .readiness-item {
            display: flex;
            align-items: flex-start;
            gap: 10px;
            padding: 10px 12px;
            border: 1px solid var(--zamp-border);
            border-radius: 12px;
            background: #fbfdff;
        }
        .readiness-dot {
            margin-top: 4px;
            width: 10px;
            height: 10px;
            border-radius: 999px;
            flex-shrink: 0;
        }
        .readiness-dot.ok { background: #15803d; box-shadow: 0 0 0 4px rgba(21, 128, 61, 0.12); }
        .readiness-dot.miss { background: #be123c; box-shadow: 0 0 0 4px rgba(190, 18, 60, 0.12); }
        .readiness-label { font-weight: 700; color: var(--zamp-text); font-size: 0.92rem; }
        .readiness-detail { color: var(--zamp-muted); font-size: 0.82rem; margin-top: 2px; }
        .queue-strip {
            display: grid;
            grid-template-columns: repeat(6, 1fr);
            gap: 10px;
            margin: 14px 0 22px;
        }
        .queue-tile {
            border: 1px solid var(--zamp-border);
            background: #ffffff;
            border-radius: 14px;
            padding: 14px;
            cursor: default;
        }
        .queue-tile.active {
            border-color: var(--zamp-blue);
            background: #eff6ff;
        }
        .queue-tile-count {
            font-size: 1.6rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            color: var(--zamp-text);
        }
        .queue-tile-label {
            color: var(--zamp-muted);
            font-size: 0.78rem;
            margin-top: 4px;
            font-weight: 700;
        }
        .recommendation-card {
            border: 1px solid var(--zamp-border);
            background: linear-gradient(135deg, rgba(31, 94, 255, 0.05), #ffffff);
            border-left: 5px solid var(--zamp-blue);
            border-radius: 16px;
            padding: 18px 20px;
            margin: 14px 0 18px;
        }
        .recommendation-eyebrow {
            color: var(--zamp-blue);
            font-size: 0.72rem;
            font-weight: 800;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            margin-bottom: 6px;
        }
        .recommendation-body {
            font-size: 1rem;
            color: var(--zamp-text);
            line-height: 1.55;
        }
        .approver-chip {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            background: #eef2ff;
            color: #3730a3;
            border-radius: 999px;
            padding: 5px 10px;
            font-weight: 700;
            font-size: 0.8rem;
            margin-top: 10px;
        }
        .queue-chip {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 10px;
            font-weight: 800;
            font-size: 0.72rem;
            letter-spacing: 0.04em;
        }
        .qc-ready { background: #dcfce7; color: var(--zamp-green); }
        .qc-ap { background: #fef3c7; color: var(--zamp-amber); }
        .qc-proc { background: #ede9fe; color: #5b21b6; }
        .qc-dup { background: #ffedd5; color: #9a3412; }
        .qc-risk { background: #ffe4e6; color: var(--zamp-red); }
        .qc-over { background: #fee2e2; color: var(--zamp-red); }
        .qc-blocked { background: #f1f5f9; color: #334155; }
        .assistant-bubble {
            background: #f8fafc;
            border: 1px solid var(--zamp-border);
            border-radius: 16px;
            padding: 16px 18px;
            margin-top: 12px;
            color: var(--zamp-text);
            line-height: 1.55;
        }
        .field-status {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 2px 8px;
            font-size: 0.7rem;
            font-weight: 800;
            letter-spacing: 0.05em;
            text-transform: uppercase;
        }
        .fs-extracted { background: #dcfce7; color: var(--zamp-green); }
        .fs-missing { background: #fee2e2; color: var(--zamp-red); }
        .fs-inferred { background: #ede9fe; color: #5b21b6; }
        .fs-suspicious { background: #fef3c7; color: var(--zamp-amber); }
        .preview-frame {
            border: 1px solid var(--zamp-border);
            border-radius: 18px;
            background: #f8fafc;
            padding: 14px;
            box-shadow: var(--zamp-shadow-soft);
        }
        .preview-frame img {
            width: 100%;
            border-radius: 12px;
            box-shadow: 0 8px 20px rgba(17, 24, 39, 0.08);
        }
        .preview-meta {
            color: var(--zamp-muted);
            font-size: 0.78rem;
            margin: 6px 0 0;
        }
        .reason-list {
            margin: 0;
            padding-left: 18px;
        }
        .reason-list li {
            margin: 6px 0;
            color: #334155;
            line-height: 1.5;
        }
        .why-panel {
            border: 1px solid var(--zamp-border);
            background: linear-gradient(135deg, rgba(31, 94, 255, 0.04), #ffffff);
            border-left: 5px solid var(--zamp-blue);
            border-radius: 16px;
            padding: 16px 20px;
            margin: 10px 0 16px;
        }
        .comment-bubble {
            border: 1px solid var(--zamp-border);
            background: #f8fafc;
            border-radius: 14px;
            padding: 12px 14px;
            margin: 8px 0;
        }
        .comment-meta {
            color: var(--zamp-muted);
            font-size: 0.78rem;
            margin-bottom: 4px;
        }
        .email-draft {
            border: 1px solid var(--zamp-border);
            background: #ffffff;
            border-radius: 14px;
            padding: 16px 18px;
            font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
            white-space: pre-wrap;
            color: var(--zamp-text);
            line-height: 1.55;
        }
        .aging-row {
            display: grid;
            grid-template-columns: 1.4fr 1fr 1fr 0.8fr 0.8fr 1fr;
            gap: 10px;
            padding: 12px 14px;
            border-bottom: 1px solid #eef2f7;
            align-items: center;
        }
        .aging-row.header {
            background: #f8fafc;
            color: #475569;
            font-size: 0.74rem;
            letter-spacing: 0.08em;
            text-transform: uppercase;
        }
        .aging-pill {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 0.74rem;
            font-weight: 800;
        }
        .age-ok { background: #dcfce7; color: var(--zamp-green); }
        .age-warn { background: #fef3c7; color: var(--zamp-amber); }
        .age-bad { background: #fee2e2; color: var(--zamp-red); }
        .summary-tiles {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 12px;
            margin: 6px 0 20px;
        }
        .summary-tile {
            background: #ffffff;
            border: 1px solid var(--zamp-border);
            border-radius: 16px;
            padding: 16px 18px;
            box-shadow: var(--zamp-shadow-soft);
        }
        .summary-tile .label {
            color: var(--zamp-muted);
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
            font-weight: 800;
        }
        .summary-tile .value {
            font-size: 1.55rem;
            font-weight: 900;
            letter-spacing: -0.03em;
            margin-top: 4px;
        }
        .summary-tile .sub {
            color: var(--zamp-muted);
            font-size: 0.8rem;
        }
        .inbox-row {
            display: grid;
            grid-template-columns: 1.2fr 2fr 1.4fr 0.9fr 0.7fr;
            gap: 10px;
            padding: 12px 14px;
            border-bottom: 1px solid #eef2f7;
            align-items: center;
        }
        .inbox-row.header {
            background: #f8fafc;
            color: #475569;
            font-size: 0.74rem;
            text-transform: uppercase;
            letter-spacing: 0.08em;
        }
        .inbox-status {
            display: inline-flex;
            align-items: center;
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 0.7rem;
            font-weight: 800;
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .ist-new { background: #eff6ff; color: var(--zamp-blue); }
        .ist-proc { background: #fef3c7; color: var(--zamp-amber); }
        .ist-rev { background: #ede9fe; color: #5b21b6; }
        .ist-paid { background: #dcfce7; color: var(--zamp-green); }
        @media (max-width: 1100px) {
            .queue-strip { grid-template-columns: repeat(3, 1fr); }
            .summary-tiles { grid-template-columns: repeat(2, 1fr); }
        }
        @media (max-width: 900px) {
            .main .block-container { padding: 22px 18px 36px; }
            .hero h1 { font-size: 1.75rem; }
            .workflow-animation { min-height: 320px; }
            .flow-node { width: 118px; }
            .readiness-grid { grid-template-columns: 1fr; }
            .queue-strip { grid-template-columns: 1fr 1fr; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_styles()


FIELD_LABELS = {
    "invoice_number": "Invoice number",
    "invoice_date": "Invoice date",
    "due_date": "Due date",
    "vendor.name": "Vendor name",
    "vendor.tax_id": "Vendor tax ID",
    "po_reference": "PO reference",
    "total": "Total",
    "subtotal": "Subtotal",
    "tax_amount": "Tax amount",
    "bank_account": "Bank account",
    "bank_ifsc": "Bank IFSC",
}


def render_pdf_preview(stored_path: str | None) -> None:
    """Render the first page of the stored PDF as a preview."""
    if not stored_path:
        st.info("Original PDF is not available for this run.")
        return
    p = Path(stored_path)
    if not p.exists():
        st.warning(f"PDF not available at {stored_path}.")
        return
    try:
        import fitz
    except ImportError:
        st.error("PyMuPDF is required to render PDF previews.")
        return
    try:
        doc = fitz.open(str(p))
        if doc.page_count == 0:
            st.warning("PDF has no pages to render.")
            return
        page = doc.load_page(0)
        pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("ascii")
        st.html(
            f'<div class="preview-frame">'
            f'<img src="data:image/png;base64,{b64}" alt="Invoice preview"/>'
            f'<p class="preview-meta">Source: {p.name} · Page 1 of {doc.page_count}</p>'
            f'</div>'
        )
        if doc.page_count > 1:
            st.caption(f"Showing first page only ({doc.page_count} pages total).")
    except Exception as exc:
        st.error(f"Could not render PDF preview: {exc}")


def field_status_chip(status: str | None) -> str:
    cls = {
        "extracted": "fs-extracted",
        "missing": "fs-missing",
        "inferred": "fs-inferred",
        "suspicious": "fs-suspicious",
    }.get(status or "extracted", "fs-extracted")
    return f'<span class="field-status {cls}">{(status or "extracted").title()}</span>'


def render_extracted_with_status(extracted: dict) -> None:
    """Tabular extracted view with per-field status pills."""
    vendor = extracted.get("vendor") or {}
    currency = extracted.get("currency", "INR")
    field_status = extracted.get("field_status") or {}

    def row(label: str, value: object, key: str) -> str:
        value_str = "<span class='subtle'>Missing</span>" if value in (None, "", 0, "0", "0.00") and (field_status.get(key) == "missing") else (str(value) if value not in (None, "") else "<span class='subtle'>—</span>")
        return f"<tr><td>{label}</td><td>{value_str}</td><td>{field_status_chip(field_status.get(key))}</td></tr>"

    rows_summary = [
        ("Invoice number", extracted.get("invoice_number"), "invoice_number"),
        ("Invoice date", extracted.get("invoice_date"), "invoice_date"),
        ("Due date", extracted.get("due_date"), "due_date"),
        ("Total", f"{currency} {float(extracted.get('total') or 0):,.2f}", "total"),
        ("Subtotal", f"{currency} {float(extracted.get('subtotal') or 0):,.2f}" if extracted.get("subtotal") is not None else None, "subtotal"),
        ("Tax amount", f"{currency} {float(extracted.get('tax_amount') or 0):,.2f}" if extracted.get("tax_amount") is not None else None, "tax_amount"),
    ]
    body = "".join(row(label, value, key) for label, value, key in rows_summary)
    st.html(
        '<div class="section-label">Invoice summary</div>'
        '<table class="field-table">'
        '<thead><tr><th>Field</th><th>Value</th><th>Status</th></tr></thead>'
        f'<tbody>{body}</tbody></table>'
    )
    rows_vendor = [
        ("Vendor name", vendor.get("name"), "vendor.name"),
        ("Vendor tax ID", vendor.get("tax_id"), "vendor.tax_id"),
        ("PO reference", extracted.get("po_reference"), "po_reference"),
        ("Bank account", extracted.get("bank_account"), "bank_account"),
        ("Bank IFSC", extracted.get("bank_ifsc"), "bank_ifsc"),
    ]
    body = "".join(row(label, value, key) for label, value, key in rows_vendor)
    st.html(
        '<div class="section-label">Vendor &amp; payment</div>'
        '<table class="field-table">'
        '<thead><tr><th>Field</th><th>Value</th><th>Status</th></tr></thead>'
        f'<tbody>{body}</tbody></table>'
    )


def render_why_this_po(decision: dict) -> None:
    po_match = decision.get("po_match") or {}
    if not po_match.get("matched"):
        st.markdown(
            '<div class="why-panel"><div class="eyebrow">Why this PO?</div>'
            f'<p>No matching PO was found. {po_match.get("notes") or ""}</p>'
            '</div>',
            unsafe_allow_html=True,
        )
        return
    reasons = po_match.get("reasons") or [po_match.get("notes")]
    bullets = "".join(f"<li>{r}</li>" for r in reasons if r)
    confidence = float(po_match.get("confidence") or 0) * 100
    record = po_match.get("po_record") or {}
    cumulative = float(po_match.get("cumulative_invoiced") or 0)
    po_amount = float(record.get("po_amount") or 0)
    st.markdown(
        f"""
        <div class="why-panel">
            <div class="eyebrow">Why this PO?</div>
            <p><strong>Matched {po_match.get('po_number')}</strong> · match type
            <code>{po_match.get('match_type')}</code> · confidence {confidence:.0f}%</p>
            <ul class="reason-list">{bullets}</ul>
            <p class="subtle">PO budget INR {po_amount:,.2f} · Cumulative approved INR {cumulative:,.2f}
            · Status {record.get('status', '—')} · Validity {record.get('valid_from','—')} → {record.get('valid_to','—')}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_duplicate_panel(decision: dict) -> None:
    dups = decision.get("duplicate_candidates") or []
    st.markdown('<div class="section-label">Duplicate similarity check</div>', unsafe_allow_html=True)
    if not dups:
        st.success("No similar invoices found in history. Duplicate risk is low.")
        return
    rows = []
    for d in dups:
        rows.append({
            "Similarity": f"{int(float(d.get('similarity', 0)) * 100)}%",
            "Prior invoice": d.get("invoice_number"),
            "Vendor": d.get("vendor_name"),
            "Amount": f"INR {float(d.get('total_amount') or 0):,.2f}" if d.get("total_amount") else "—",
            "Received": d.get("uploaded_at", "—")[:19] if d.get("uploaded_at") else "—",
            "Why flagged": d.get("reason"),
            "Run ID": d.get("run_id"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def build_vendor_email_draft(decision: dict) -> tuple[str, str]:
    extracted = decision.get("extracted") or {}
    vendor = extracted.get("vendor") or {}
    invoice_no = extracted.get("invoice_number") or "(no invoice number)"
    vendor_name = vendor.get("name") or "Vendor"
    currency = extracted.get("currency", "INR")
    total = float(extracted.get("total") or 0)
    missing = extracted.get("missing_fields") or []
    status = decision.get("status")
    readiness = decision.get("readiness") or {}
    blockers = readiness.get("blockers") or []

    if missing:
        subject = f"Missing information for invoice {invoice_no}"
        readable = ", ".join(
            FIELD_LABELS.get(m, m.replace("_", " ").title()) for m in missing
        )
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"Thanks for sending invoice {invoice_no} for {currency} {total:,.2f}. "
            f"Before we can process payment, we need a few clarifications:\n\n"
            f"  • {readable}\n\n"
            f"Please confirm the missing values (especially the PO reference and supporting tax ID) "
            f"so we can match it to the approved PO and release payment.\n\n"
            f"Thank you,\nAccounts Payable Team"
        )
    elif status == "REJECTED":
        subject = f"Invoice {invoice_no} cannot be processed"
        reasons = "\n".join(f"  • {b}" for b in blockers) or "  • Validation rules failed."
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"We received invoice {invoice_no} for {currency} {total:,.2f}, but we cannot process it "
            f"at this time for the following reasons:\n\n{reasons}\n\n"
            f"Please review the invoice and re-issue once corrected. Reach out if you have questions.\n\n"
            f"Thank you,\nAccounts Payable Team"
        )
    elif status == "FLAGGED":
        subject = f"Quick clarification on invoice {invoice_no}"
        reason = blockers[0] if blockers else (decision.get("reasoning") or "An internal check could not be completed.")
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"We received invoice {invoice_no} for {currency} {total:,.2f}. It is on hold pending one "
            f"clarification:\n\n  • {reason}\n\n"
            f"Could you confirm so we can release payment per the contracted terms?\n\n"
            f"Thank you,\nAccounts Payable Team"
        )
    else:
        subject = f"Invoice {invoice_no} approved for payment"
        body = (
            f"Hi {vendor_name} team,\n\n"
            f"Invoice {invoice_no} for {currency} {total:,.2f} has been approved and is scheduled for "
            f"payment per our contracted terms.\n\nThank you,\nAccounts Payable Team"
        )
    return subject, body


SEED_EMAILS: list[dict] = [
    {
        "filename": "01_happy_path_acme.pdf",
        "sender": "billing@acmesteel.in",
        "subject": "Invoice ACME-2026-001 for May steel order",
        "body": "Hi Team,\n\nPlease find attached our invoice for the May steel shipment against PO-2026-0068. Kindly confirm receipt.\n\nRegards,\nAcme Steel AR",
        "vendor_guess": "Acme Steel Pvt Ltd",
    },
    {
        "filename": "02_amount_mismatch_globaloffice.pdf",
        "sender": "ar@globaloffice.in",
        "subject": "May invoice - GO-2026-554",
        "body": "Hi AP,\n\nAttaching our May invoice for the office supplies order. Please process at the earliest.\n\nThanks,\nGlobal Office Supplies",
        "vendor_guess": "Global Office Supplies",
    },
    {
        "filename": "03_wrong_bank_techsource.pdf",
        "sender": "accounts@techsource-new.com",
        "subject": "Updated invoice TS-2026-100 - please pay to new account",
        "body": "Hello,\n\nWe have updated our banking details. Please remit payment to the new account on the invoice.\n\nBest,\nTechSource Finance",
        "vendor_guess": "TechSource India",
    },
    {
        "filename": "04_duplicate_pinepaper.pdf",
        "sender": "billing@pinepaper.in",
        "subject": "Resending April invoice PP-2026-077",
        "body": "Hi Team,\n\nResending in case the earlier one did not arrive. Please process at your convenience.\n\nThanks,\nPine Paper",
        "vendor_guess": "Pine Paper Mills",
    },
    {
        "filename": "05_missing_po_recurring_saas.pdf",
        "sender": "ar@recurringsaas.in",
        "subject": "Monthly subscription invoice RS-2026-009",
        "body": "Hi Finance,\n\nAttaching our recurring monthly subscription invoice. No PO is printed but please apply to our ongoing annual contract.\n\nWarm regards,\nRecurringSaaS AR",
        "vendor_guess": "RecurringSaaS India Pvt Ltd",
    },
    {
        "filename": "06_scanned_freight.pdf",
        "sender": "shipping@freightcoindia.com",
        "subject": "Scanned freight invoice FRT-2026-220",
        "body": "Hi,\n\nPlease find scanned freight invoice attached. Original is in transit by courier.\n\nThanks,\nFreightCo",
        "vendor_guess": "FreightCo India",
    },
    {
        "filename": "07_missing_invoice_number_consulting.pdf",
        "sender": "studio@brightconsulting.in",
        "subject": "Consulting fees - May",
        "body": "Hello,\n\nAttaching consulting fee invoice for May. Number will be issued shortly; please process to keep payment on schedule.\n\nThank you,\nBright Consulting",
        "vendor_guess": "Bright Consulting",
    },
]


def seed_inbox_emails() -> int:
    """Populate inbox_emails with sample emails for sample invoices that exist on disk."""
    INBOX_PDF_DIR.mkdir(parents=True, exist_ok=True)
    inserted = 0
    existing = {row["attachment_name"] for row in db.list_inbox()}
    for idx, seed in enumerate(SEED_EMAILS):
        if seed["filename"] in existing:
            continue
        src = SAMPLE_PDF_DIR / seed["filename"]
        if not src.exists():
            continue
        dest = INBOX_PDF_DIR / seed["filename"]
        if not dest.exists():
            import shutil as _shutil
            _shutil.copyfile(src, dest)
        db.upsert_inbox_email(
            {
                "id": str(uuid.uuid4()),
                "received_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                "sender": seed["sender"],
                "subject": seed["subject"],
                "body": seed["body"],
                "attachment_name": seed["filename"],
                "vendor_guess": seed["vendor_guess"],
                "status": "New",
                "run_id": None,
                "pdf_path": str(dest),
            }
        )
        inserted += 1
    return inserted


def days_between(value: str | None, today: date | None = None) -> int | None:
    if not value:
        return None
    today = today or datetime.now(timezone.utc).date()
    try:
        d = datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except Exception:
        try:
            d = datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
        except Exception:
            return None
    return (today - d).days


def days_until(value: str | None, today: date | None = None) -> int | None:
    days = days_between(value, today)
    return -days if days is not None else None


WORKFLOW_OWNERS = [
    "AP Manager",
    "Procurement Owner",
    "Vendor Master",
    "Finance Controller",
    "Compliance",
]

WORKFLOW_STATES = [
    "Open",
    "Waiting for Vendor",
    "Waiting for Procurement",
    "Approved",
    "Rejected",
]


def default_owner_and_state(decision: dict) -> tuple[str, str]:
    readiness = decision.get("readiness") or {}
    queue = readiness.get("queue") or ""
    if queue == "Ready for Payment":
        return "AP Manager", "Approved"
    if queue == "Needs Procurement Review":
        return "Procurement Owner", "Waiting for Procurement"
    if queue == "Vendor/Bank Risk":
        return "Vendor Master", "Waiting for Vendor"
    if queue == "Possible Duplicate":
        return "AP Manager", "Open"
    if queue == "Payment Blocked":
        return "Compliance", "Rejected"
    if queue == "Over PO Limit":
        return "Procurement Owner", "Waiting for Procurement"
    return "AP Manager", "Open"


def render_topbar() -> None:
    st.markdown(
        """
        <div class="topbar">
            <div class="brand-lockup">
                <span class="brand-mark">Z</span>
                <span>Zamp AP Automation</span>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_hero(title: str, subtitle: str) -> None:
    render_topbar()
    st.markdown(
        f"""
        <div class="hero">
            <div class="eyebrow">Zamp AI AP Operations</div>
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(status: str) -> str:
    return {"APPROVED": "Auto approved", "FLAGGED": "Needs review", "REJECTED": "Payment blocked"}.get(status, status)


def status_class(status: str) -> str:
    return {"APPROVED": "approved", "FLAGGED": "flagged", "REJECTED": "rejected"}.get(status, "flagged")


def render_decision_card(decision: dict) -> None:
    status = decision["status"]
    klass = status_class(status)
    st.markdown(
        f"""
        <div class="decision-card decision-{klass}">
            <span class="pill pill-{klass}">{status}</span>
            <div class="decision-title">{status_badge(status)}</div>
            <p class="decision-copy">{decision["reasoning"]}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    c1, c2, c3, c4 = st.columns(4)
    extracted = decision["extracted"]
    c1.metric("Vendor", extracted["vendor"].get("name") or "Unknown")
    c2.metric("Invoice", extracted.get("invoice_number") or "Missing")
    c3.metric("Total", f"{extracted.get('currency', 'INR')} {float(extracted['total']):,.2f}")
    c4.metric("Confidence", f"{decision['confidence']:.0%}")
    render_payment_readiness(decision)
    render_recommendation(decision)


def render_stage_timeline(events: list[dict]) -> None:
    st.markdown('<div class="panel"><h3>Live Processing Trace</h3>', unsafe_allow_html=True)
    for event in events:
        detail = event.get("output_summary") or event.get("input_summary") or "Completed"
        st.markdown(
            f"""
            <div class="stage-row">
                <div class="stage-name">{event["stage_name"]}</div>
                <div class="stage-detail">{detail}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    st.markdown("</div>", unsafe_allow_html=True)


def _display_value(value: object) -> str:
    if value is None or value == "":
        return '<span class="status-chip">Missing</span>'
    if isinstance(value, float):
        return f"{value:,.2f}"
    return str(value)


def render_field_table(title: str, rows: list[tuple[str, object]]) -> None:
    body = "".join(
        f"<tr><td>{label}</td><td>{_display_value(value)}</td></tr>"
        for label, value in rows
    )
    st.markdown(
        f"""
        <div class="section-label">{title}</div>
        <table class="field-table">
            <thead><tr><th>Field</th><th>Value</th></tr></thead>
            <tbody>{body}</tbody>
        </table>
        """,
        unsafe_allow_html=True,
    )


def render_extracted_invoice(extracted: dict) -> None:
    vendor = extracted.get("vendor") or {}
    currency = extracted.get("currency", "INR")
    render_field_table(
        "Invoice summary",
        [
            ("Invoice number", extracted.get("invoice_number")),
            ("Invoice date", extracted.get("invoice_date")),
            ("Due date", extracted.get("due_date")),
            ("Total", f"{currency} {float(extracted.get('total') or 0):,.2f}"),
            ("Subtotal", f"{currency} {float(extracted.get('subtotal') or 0):,.2f}" if extracted.get("subtotal") is not None else None),
            ("Tax amount", f"{currency} {float(extracted.get('tax_amount') or 0):,.2f}" if extracted.get("tax_amount") is not None else None),
            ("Tax rate", f"{extracted.get('tax_rate')}%" if extracted.get("tax_rate") is not None else None),
            ("Extraction confidence", f"{float(extracted.get('extraction_confidence') or 0):.0%}"),
        ],
    )
    render_field_table(
        "Vendor, PO, and payment details",
        [
            ("Vendor name", vendor.get("name")),
            ("Vendor tax ID", vendor.get("tax_id")),
            ("Vendor email", vendor.get("email")),
            ("PO reference", extracted.get("po_reference")),
            ("Bank account", extracted.get("bank_account")),
            ("Bank IFSC", extracted.get("bank_ifsc")),
            ("Source type", extracted.get("source_type")),
            ("Missing fields", ", ".join(extracted.get("missing_fields") or []) or None),
        ],
    )
    line_items = extracted.get("line_items") or []
    if line_items:
        frame = pd.DataFrame(line_items)
        st.markdown('<div class="section-label">Line items</div>', unsafe_allow_html=True)
        st.dataframe(frame, use_container_width=True, hide_index=True)
    if extracted.get("raw_notes"):
        render_field_table("Extraction notes", [("Notes", extracted.get("raw_notes"))])


def format_runs(frame: pd.DataFrame) -> pd.DataFrame:
    display = frame.copy()
    if "confidence" in display:
        display["confidence"] = display["confidence"].map(lambda value: f"{float(value):.0%}" if pd.notna(value) else "")
    if "total_amount" in display:
        display["total_amount"] = display["total_amount"].map(lambda value: f"INR {float(value):,.2f}" if pd.notna(value) else "")
    rename = {
        "uploaded_at": "Processed at",
        "vendor_name": "Vendor",
        "invoice_number": "Invoice",
        "total_amount": "Amount",
        "status": "Decision",
        "po_reference": "PO",
        "confidence": "Confidence",
        "id": "Run ID",
    }
    columns = [key for key in rename if key in display.columns]
    return display[columns].rename(columns=rename)


QUEUE_CLASS = {
    "Ready for Payment": "qc-ready",
    "Needs AP Review": "qc-ap",
    "Needs Procurement Review": "qc-proc",
    "Possible Duplicate": "qc-dup",
    "Vendor/Bank Risk": "qc-risk",
    "Over PO Limit": "qc-over",
    "Payment Blocked": "qc-blocked",
}

QUEUE_ORDER = [
    "Ready for Payment",
    "Needs AP Review",
    "Needs Procurement Review",
    "Possible Duplicate",
    "Vendor/Bank Risk",
    "Over PO Limit",
]

OVERRIDE_REASONS = [
    "Business approved PO variance",
    "Duplicate false positive",
    "Vendor bank updated",
    "Emergency payment",
    "Procurement exception approved",
    "Other (specify)",
]


def queue_for(decision: dict) -> str:
    readiness = decision.get("readiness") or {}
    return readiness.get("queue") or ("Payment Blocked" if decision.get("status") == "REJECTED" else "Needs AP Review")


def safe_lower(value: object) -> str:
    return str(value or "").strip().lower()


def render_payment_readiness(decision: dict) -> None:
    readiness = decision.get("readiness")
    if not readiness:
        return
    score = int(readiness.get("score") or 0)
    queue = readiness.get("queue", "Needs AP Review")
    queue_class = QUEUE_CLASS.get(queue, "qc-ap")
    items_html = "".join(
        f"""
        <div class="readiness-item">
            <div class="readiness-dot {'ok' if check['passed'] else 'miss'}"></div>
            <div>
                <div class="readiness-label">{check['label']}</div>
                <div class="readiness-detail">{check['detail']}</div>
            </div>
        </div>
        """
        for check in readiness.get("checks", [])
    )
    st.markdown(
        f"""
        <div class="readiness-card">
            <div class="readiness-head">
                <div>
                    <div class="eyebrow">Payment Readiness</div>
                    <div class="readiness-score">Ready to Pay: {score}%</div>
                </div>
                <span class="queue-chip {queue_class}">{queue}</span>
            </div>
            <div class="readiness-bar"><div class="readiness-fill" style="width: {score}%"></div></div>
            <div class="readiness-grid">{items_html}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_recommendation(decision: dict) -> None:
    readiness = decision.get("readiness") or {}
    recommendation = readiness.get("recommendation") or decision.get("next_action") or ""
    approver = readiness.get("approver") or "AP Manager"
    st.markdown(
        f"""
        <div class="recommendation-card">
            <div class="recommendation-eyebrow">Payment Recommendation</div>
            <div class="recommendation-body">{recommendation}</div>
            <span class="approver-chip">Suggested approver: {approver}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def build_audit_report_html(decision: dict, events: list[dict]) -> str:
    extracted = decision.get("extracted") or {}
    vendor = extracted.get("vendor") or {}
    readiness = decision.get("readiness") or {}
    rows_invoice = [
        ("Invoice number", extracted.get("invoice_number")),
        ("Invoice date", extracted.get("invoice_date")),
        ("Vendor", vendor.get("name")),
        ("Vendor tax ID", vendor.get("tax_id")),
        ("Total", f"{extracted.get('currency', 'INR')} {float(extracted.get('total') or 0):,.2f}"),
        ("PO reference", extracted.get("po_reference")),
        ("Bank account", extracted.get("bank_account")),
        ("Decision", decision.get("status")),
        ("Confidence", f"{float(decision.get('confidence') or 0):.0%}"),
        ("Queue", readiness.get("queue")),
        ("Suggested approver", readiness.get("approver")),
        ("Readiness score", f"{readiness.get('score', 0)}%"),
    ]

    def section(title: str, rows: list[tuple[str, object]]) -> str:
        body = "".join(f"<tr><td>{k}</td><td>{v if v is not None else '-'}</td></tr>" for k, v in rows)
        return f"<h3>{title}</h3><table>{body}</table>"

    validations_rows = [
        (f"{v['rule_id']} {v['rule_name']}", ("PASS" if v["passed"] else "FAIL") + f" — {v['detail']}")
        for v in decision.get("validations", [])
    ]
    events_rows = [
        (e.get("stage_name"), f"{e.get('status')} — {e.get('output_summary') or '-'}")
        for e in events
    ]
    return f"""
    <html><head><meta charset="utf-8"><title>Audit Report {decision.get('invoice_id')}</title>
    <style>
      body {{ font-family: Inter, Arial, sans-serif; margin: 32px; color: #111827; }}
      h1 {{ margin: 0 0 4px; letter-spacing: -0.02em; }}
      h3 {{ margin: 22px 0 8px; }}
      p.sub {{ color: #6b7280; margin: 0 0 18px; }}
      table {{ width: 100%; border-collapse: collapse; margin-bottom: 12px; }}
      th, td {{ border-bottom: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; vertical-align: top; }}
      td:first-child {{ width: 32%; color: #475569; }}
      .pill {{ display: inline-block; padding: 4px 10px; border-radius: 999px; font-weight: 700; }}
      .approved {{ background: #dcfce7; color: #166534; }}
      .flagged {{ background: #fef3c7; color: #92400e; }}
      .rejected {{ background: #ffe4e6; color: #9f1239; }}
    </style></head>
    <body>
      <h1>Zamp AP Audit Report</h1>
      <p class="sub">Run ID {decision.get('invoice_id')} · Generated {decision.get('timestamp')}</p>
      <span class="pill {decision.get('status','').lower()}">{decision.get('status')}</span>
      <h3>Recommendation</h3>
      <p>{readiness.get('recommendation') or decision.get('next_action')}</p>
      {section('Invoice Summary', rows_invoice)}
      {section('Validations', validations_rows)}
      {section('Audit Trail', events_rows)}
    </body></html>
    """


def export_payment_batch_csv(decisions: list[dict]) -> str:
    rows = []
    for d in decisions:
        extracted = d.get("extracted") or {}
        vendor = extracted.get("vendor") or {}
        readiness = d.get("readiness") or {}
        if readiness.get("queue") != "Ready for Payment" and d.get("overridden_status") != "APPROVED":
            continue
        rows.append({
            "invoice_id": d.get("invoice_id"),
            "invoice_number": extracted.get("invoice_number"),
            "vendor_name": vendor.get("name"),
            "vendor_tax_id": vendor.get("tax_id"),
            "po_reference": extracted.get("po_reference"),
            "amount": float(extracted.get("total") or 0),
            "currency": extracted.get("currency") or "INR",
            "bank_account": extracted.get("bank_account"),
            "bank_ifsc": extracted.get("bank_ifsc"),
            "invoice_date": extracted.get("invoice_date"),
            "due_date": extracted.get("due_date"),
        })
    if not rows:
        return ""
    return pd.DataFrame(rows).to_csv(index=False)


def answer_question(query: str, decisions: list[dict]) -> str:
    q = (query or "").strip().lower()
    if not q:
        return "Ask about an invoice, vendor, PO, or queue."
    if "ready to pay" in q or "ready for payment" in q:
        ready = [d for d in decisions if queue_for(d) == "Ready for Payment"]
        if not ready:
            return "No invoices are currently ready to pay."
        lines = [f"- {d['extracted'].get('invoice_number')} from {d['extracted']['vendor'].get('name')} for {d['extracted'].get('currency','INR')} {float(d['extracted'].get('total',0)):,.2f}" for d in ready[:10]]
        return f"There are {len(ready)} invoices ready to pay:\n" + "\n".join(lines)
    if "exceeding po" in q or "over po" in q or "tolerance" in q:
        over = [d for d in decisions if queue_for(d) == "Over PO Limit"]
        if not over:
            return "No invoices are currently exceeding PO tolerance."
        return f"{len(over)} invoice(s) exceed PO tolerance: " + ", ".join(d["extracted"].get("invoice_number") or "—" for d in over[:10])
    if "duplicate" in q:
        dup = [d for d in decisions if queue_for(d) == "Possible Duplicate"]
        return f"{len(dup)} invoice(s) flagged as possible duplicates." if dup else "No possible duplicates."
    if "consumed on" in q or "remaining on" in q or "po-" in q:
        import re
        match = re.search(r"po-?\s*\d{4}-?\s*\d{4}", q, re.IGNORECASE)
        if match:
            po_number = match.group(0).upper().replace(" ", "")
            if not po_number.startswith("PO-"):
                po_number = po_number.replace("PO", "PO-", 1) if "-" not in po_number else po_number
            related = [d for d in decisions if (d["extracted"].get("po_reference") or "").upper() == po_number]
            consumed = sum(float(d["extracted"].get("total") or 0) for d in related if d.get("status") == "APPROVED")
            return f"PO {po_number}: {len(related)} invoice(s) recorded. Approved consumed total: INR {consumed:,.2f}."
        return "Provide the PO number in the form PO-2026-0014."
    if "why" in q and ("reject" in q or "block" in q or "flag" in q):
        recent = sorted(decisions, key=lambda d: d.get("timestamp") or "", reverse=True)
        for d in recent:
            if d.get("status") in {"REJECTED", "FLAGGED"}:
                return f"Invoice {d['extracted'].get('invoice_number')} from {d['extracted']['vendor'].get('name')} was {d['status'].lower()}. {d.get('reasoning')}"
        return "No rejected or flagged invoices in history."
    if "summary" in q or "queue" in q or "status" in q:
        counts: dict[str, int] = {}
        for d in decisions:
            counts[queue_for(d)] = counts.get(queue_for(d), 0) + 1
        return "Queue summary: " + ", ".join(f"{k}: {v}" for k, v in counts.items()) if counts else "No invoices processed."
    return "I can answer questions about ready-to-pay invoices, PO consumption, tolerance issues, duplicates, and recent rejections."


def local_process(uploaded_file) -> tuple[dict, list[dict]]:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
        tmp.write(uploaded_file.getvalue())
        tmp_path = Path(tmp.name)
    try:
        decision, events = process_invoice(tmp_path, uploaded_file.name)
        return decision.model_dump(mode="json"), [e.model_dump(mode="json") for e in events]
    finally:
        tmp_path.unlink(missing_ok=True)


def upload_page() -> None:
    render_hero(
        "Invoice triage that looks audit-ready.",
        "Upload a vendor invoice and watch Zamp's AP workflow classify, extract, match, validate, decide, and persist every step.",
    )
    left, right = st.columns([1.05, 0.95], gap="large")
    with left:
        st.markdown(
            """
            <div class="panel upload-panel">
                <h3>Start a payables run</h3>
                <p class="subtle">Upload an invoice PDF to trigger the AP automation workflow.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        uploaded = st.file_uploader("Invoice PDF", type=["pdf"], label_visibility="collapsed")
        run_clicked = st.button("Run AP decisioning", type="primary", use_container_width=True, disabled=uploaded is None)
    with right:
        st.markdown(
            """
            <div class="panel workflow-animation">
                <div class="flow-line line-a"></div>
                <div class="flow-line line-b"></div>
                <div class="flow-line line-c"></div>
                <div class="flow-line line-d"></div>
                <div class="pulse-dot"></div>
                <div class="pulse-dot two"></div>
                <div class="pulse-dot three"></div>
                <div class="flow-node node-invoice"><span>01</span><span>Invoice</span></div>
                <div class="flow-node node-extract"><span>02</span><span>Extract</span></div>
                <div class="flow-node node-controls"><span>03</span><span>Controls</span></div>
                <div class="flow-node node-decision"><span>04</span><span>Decision</span></div>
                <div class="decision-orb">Audit-ready output</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    if uploaded and run_clicked:
        with st.status("Running Zamp AP workflow", expanded=True) as status:
            decision, events = local_process(uploaded)
            for event in events:
                st.write(f"{event['stage_name']}: {event.get('output_summary') or 'complete'}")
            status.update(label="Decision ready", state="complete")
        render_decision_card(decision)
        render_stage_timeline(events)
        tab1, tab2 = st.tabs(["Extracted invoice", "Audit event table"])
        with tab1:
            render_extracted_invoice(decision["extracted"])
        with tab2:
            st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)


def queue_counts(decisions: list[dict]) -> dict[str, int]:
    counts = {q: 0 for q in QUEUE_ORDER}
    counts["Payment Blocked"] = 0
    for d in decisions:
        counts[queue_for(d)] = counts.get(queue_for(d), 0) + 1
    return counts


def all_decisions() -> list[dict]:
    return [d.model_dump(mode="json") for d in db.get_all_decisions()]


def queue_page() -> None:
    render_hero(
        "Exception queue.",
        "Sort live invoices by the action needed: ready to pay, review, procurement, duplicates, vendor risk, and over-PO exceptions.",
    )
    decisions = all_decisions()
    if not decisions:
        st.info("No processed invoices yet. Upload a PDF to start.")
        return
    counts = queue_counts(decisions)
    selected = st.session_state.get("queue_filter", "Ready for Payment")
    tiles_html = ""
    for q in QUEUE_ORDER:
        cls = "active" if q == selected else ""
        tiles_html += (
            f'<div class="queue-tile {cls}">'
            f'<div class="queue-tile-count">{counts.get(q, 0)}</div>'
            f'<div class="queue-tile-label">{q}</div>'
            '</div>'
        )
    st.html(f'<div class="queue-strip">{tiles_html}</div>')

    selected = st.selectbox("Filter by queue", QUEUE_ORDER + ["Payment Blocked"], index=(QUEUE_ORDER + ["Payment Blocked"]).index(selected) if selected in (QUEUE_ORDER + ["Payment Blocked"]) else 0)
    st.session_state["queue_filter"] = selected

    filtered = [d for d in decisions if queue_for(d) == selected]
    if not filtered:
        st.info(f"No invoices currently in {selected}.")
    else:
        rows = []
        for d in filtered:
            extracted = d.get("extracted") or {}
            vendor = extracted.get("vendor") or {}
            readiness = d.get("readiness") or {}
            rows.append({
                "Run ID": d.get("invoice_id"),
                "Vendor": vendor.get("name"),
                "Invoice": extracted.get("invoice_number"),
                "Amount": f"{extracted.get('currency', 'INR')} {float(extracted.get('total') or 0):,.2f}",
                "PO": extracted.get("po_reference"),
                "Readiness": f"{readiness.get('score', 0)}%",
                "Approver": readiness.get("approver"),
                "Recommendation": (readiness.get("recommendation") or "")[:120],
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        target = st.selectbox("Open invoice", [r["Run ID"] for r in rows], label_visibility="collapsed")
        if target and st.button("Open in detail", use_container_width=True):
            st.session_state["selected_run"] = target

    st.markdown("---")
    st.subheader("Payment Batch Export")
    st.caption("Export all invoices in the Ready for Payment queue as a payment batch CSV.")
    csv = export_payment_batch_csv(decisions)
    if csv:
        st.download_button(
            "Download payment batch CSV",
            data=csv,
            file_name="zamp_payment_batch.csv",
            mime="text/csv",
            type="primary",
        )
    else:
        st.info("No invoices ready to pay yet.")


def detail_page() -> None:
    render_hero(
        "Invoice investigation workspace.",
        "Compare the original PDF with extracted fields, see why each PO was chosen, review duplicate candidates, assign workflow owners, and draft vendor communication — all in one place.",
    )
    runs = db.list_runs()
    ids = [r.id for r in runs]
    default = st.session_state.get("selected_run") if st.session_state.get("selected_run") in ids else (ids[0] if ids else None)
    if not default:
        st.info("No invoice is available yet.")
        return
    run_id = st.selectbox("Run", ids, index=ids.index(default))
    decision = db.get_decision(run_id)
    events = db.get_events(run_id)
    if not decision:
        st.error("Run not found.")
        return
    decision_data = decision.model_dump(mode="json")
    render_decision_card(decision_data)

    tab_review, tab_decision, tab_workflow, tab_email, tab_audit = st.tabs([
        "Review (side-by-side)",
        "Decision detail",
        "Workflow",
        "Vendor email",
        "Audit & report",
    ])

    with tab_review:
        left, right = st.columns([1.05, 0.95], gap="large")
        with left:
            st.markdown('<div class="section-label">Original invoice</div>', unsafe_allow_html=True)
            render_pdf_preview(decision_data.get("stored_path"))
        with right:
            render_extracted_with_status(decision_data["extracted"])
            line_items = decision_data["extracted"].get("line_items") or []
            if line_items:
                st.markdown('<div class="section-label">Line items</div>', unsafe_allow_html=True)
                st.dataframe(pd.DataFrame(line_items), use_container_width=True, hide_index=True)
            if decision_data["extracted"].get("raw_notes"):
                st.caption(decision_data["extracted"].get("raw_notes"))

    with tab_decision:
        render_why_this_po(decision_data)
        render_duplicate_panel(decision_data)
        st.markdown('<div class="section-label">Control results</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(decision_data["validations"]), use_container_width=True, hide_index=True)

    with tab_workflow:
        st.markdown(
            '<div class="panel"><h3>Exception workflow</h3>'
            '<p class="subtle">Assign owner, track status, leave comments, and apply human override.</p></div>',
            unsafe_allow_html=True,
        )
        wf = db.get_workflow(run_id) or {}
        default_owner, default_state = default_owner_and_state(decision_data)
        owner_val = wf.get("owner") or default_owner
        state_val = wf.get("state") or default_state
        c1, c2 = st.columns(2)
        with c1:
            owner = st.selectbox(
                "Owner",
                WORKFLOW_OWNERS,
                index=WORKFLOW_OWNERS.index(owner_val) if owner_val in WORKFLOW_OWNERS else 0,
            )
        with c2:
            state = st.selectbox(
                "Status",
                WORKFLOW_STATES,
                index=WORKFLOW_STATES.index(state_val) if state_val in WORKFLOW_STATES else 0,
            )
        if st.button("Save workflow assignment", type="primary"):
            db.set_workflow(run_id, owner, state)
            st.success(f"Owner {owner} · status {state} saved.")

        st.markdown('<div class="section-label">Comment history</div>', unsafe_allow_html=True)
        comments = db.list_comments(run_id)
        if comments:
            for c in comments:
                st.markdown(
                    f'<div class="comment-bubble"><div class="comment-meta">{c["author"]} · {c["created_at"][:19]}</div>{c["body"]}</div>',
                    unsafe_allow_html=True,
                )
        else:
            st.caption("No comments yet.")

        author = st.text_input("Your name", "ap_manager_demo", key=f"author_{run_id}")
        body = st.text_area("Add a comment", placeholder="e.g. Waiting on procurement to extend PO budget…", key=f"body_{run_id}")
        if st.button("Post comment") and body.strip():
            db.add_comment(run_id, author, body.strip())
            st.success("Comment added.")
            st.rerun()

        st.markdown("---")
        st.markdown('<div class="section-label">Override machine decision</div>', unsafe_allow_html=True)
        new_status = st.selectbox("Override status", ["APPROVED", "FLAGGED", "REJECTED"], key=f"ovr_status_{run_id}")
        reason_choice = st.selectbox("Reason", OVERRIDE_REASONS, key=f"ovr_reason_{run_id}")
        custom = st.text_area("Additional notes", placeholder="Optional context for auditors", key=f"ovr_notes_{run_id}")
        user = st.text_input("Overridden by", "ap_manager_demo", key=f"ovr_user_{run_id}")
        if st.button("Save override", type="primary", key=f"ovr_save_{run_id}"):
            full_reason = reason_choice if reason_choice != "Other (specify)" else (custom or "Other")
            if custom and reason_choice != "Other (specify)":
                full_reason = f"{reason_choice}: {custom}"
            db.override_run(run_id, new_status, full_reason, user)
            st.success("Override recorded.")

    with tab_email:
        st.markdown(
            '<div class="panel"><h3>Vendor communication draft</h3>'
            '<p class="subtle">Auto-generated email based on what is missing or flagged. Edit before sending.</p></div>',
            unsafe_allow_html=True,
        )
        subject, body = build_vendor_email_draft(decision_data)
        subject_state = st.text_input("Subject", value=subject, key=f"email_subject_{run_id}")
        body_state = st.text_area("Body", value=body, height=320, key=f"email_body_{run_id}")
        c1, c2 = st.columns([1, 1])
        with c1:
            st.download_button(
                "Download as .eml",
                data=f"Subject: {subject_state}\n\n{body_state}",
                file_name=f"vendor_email_{decision_data.get('invoice_id')}.eml",
                mime="message/rfc822",
                type="primary",
            )
        vendor_email = (decision_data.get("extracted") or {}).get("vendor", {}).get("email") or ""
        if vendor_email:
            with c2:
                from urllib.parse import quote
                mailto = f"mailto:{vendor_email}?subject={quote(subject_state)}&body={quote(body_state)}"
                st.markdown(f'<a class="stButton" href="{mailto}"><button>Open in email client</button></a>', unsafe_allow_html=True)

    with tab_audit:
        render_stage_timeline(events)
        st.dataframe(pd.DataFrame(events), use_container_width=True, hide_index=True)
        st.markdown("---")
        html = build_audit_report_html(decision_data, events)
        st.download_button(
            "Download audit report (HTML)",
            data=html,
            file_name=f"audit_{decision_data.get('invoice_id')}.html",
            mime="text/html",
            type="primary",
        )
        st.components.v1.html(html, height=620, scrolling=True)


def po_consumption_page() -> None:
    render_hero(
        "PO consumption.",
        "Compare PO budgets to invoiced spend, see remaining balance, and spot invoices that would exceed the PO.",
    )
    pos = pd.read_csv("data/pos.csv")
    decisions = all_decisions()
    rows = []
    for _, po in pos.iterrows():
        po_number = po["po_number"]
        related = [d for d in decisions if (d.get("extracted") or {}).get("po_reference") == po_number]
        invoiced_approved = sum(float((d.get("extracted") or {}).get("total") or 0) for d in related if d.get("status") == "APPROVED")
        invoiced_pending = sum(float((d.get("extracted") or {}).get("total") or 0) for d in related if d.get("status") in {"FLAGGED"})
        po_amount = float(po["po_amount"])
        tolerance = float(po["tolerance_pct"]) / 100
        cap = po_amount * (1 + tolerance)
        remaining = po_amount - invoiced_approved
        exceedance = max(0.0, (invoiced_approved + invoiced_pending) - cap)
        rows.append({
            "PO": po_number,
            "Vendor": po["vendor_name"],
            "PO Amount": f"INR {po_amount:,.2f}",
            "Approved invoiced": f"INR {invoiced_approved:,.2f}",
            "Pending review": f"INR {invoiced_pending:,.2f}",
            "Remaining (approved)": f"INR {remaining:,.2f}",
            "Tolerance cap": f"INR {cap:,.2f}",
            "Exceedance": f"INR {exceedance:,.2f}" if exceedance else "—",
            "Status": po["status"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("### Drilldown")
    selected_po = st.selectbox("Pick a PO", pos["po_number"].tolist())
    invoices = db.get_po_invoices(selected_po)
    if invoices:
        drill_rows = []
        for inv in invoices:
            drill_rows.append({
                "Invoice": inv.get("invoice_number"),
                "Vendor": inv.get("vendor_name"),
                "Amount": f"{inv.get('currency','INR')} {float(inv.get('total_amount') or 0):,.2f}",
                "Status": inv.get("overridden_status") or inv.get("status"),
                "Processed at": inv.get("uploaded_at"),
                "Run ID": inv.get("id"),
            })
        st.dataframe(pd.DataFrame(drill_rows), use_container_width=True, hide_index=True)
    else:
        st.info("No invoices recorded against this PO yet.")


def vendor_risk_page() -> None:
    render_hero(
        "Vendor risk panel.",
        "See vendor master status, bank/tax verification, prior duplicates, rejection history, and payment trend.",
    )
    vendors = pd.read_csv("data/approved_vendors.csv")
    decisions = all_decisions()
    rows = []
    for _, v in vendors.iterrows():
        vendor_name = v["vendor_name"]
        history = [
            d
            for d in decisions
            if safe_lower(((d.get("extracted") or {}).get("vendor") or {}).get("name"))
            == safe_lower(vendor_name)
        ]
        approved = sum(1 for d in history if d.get("status") == "APPROVED")
        flagged = sum(1 for d in history if d.get("status") == "FLAGGED")
        rejected = sum(1 for d in history if d.get("status") == "REJECTED")
        duplicates = sum(1 for d in history if queue_for(d) == "Possible Duplicate")
        bank_ok = "Yes" if str(v.get("active")).lower() == "true" else "Inactive"
        total_paid = sum(float((d.get("extracted") or {}).get("total") or 0) for d in history if d.get("status") == "APPROVED")
        rows.append({
            "Vendor": vendor_name,
            "Active": "Active" if str(v.get("active")).lower() == "true" else "Inactive",
            "Tax ID": v.get("tax_id"),
            "Bank account": v.get("bank_account"),
            "Bank IFSC": v.get("bank_ifsc"),
            "Invoices": len(history),
            "Approved": approved,
            "Flagged": flagged,
            "Rejected": rejected,
            "Duplicates": duplicates,
            "Total paid (INR)": f"{total_paid:,.2f}",
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    st.markdown("### Vendor history drilldown")
    pick = st.selectbox("Vendor", vendors["vendor_name"].tolist())
    history = db.get_vendor_invoices(pick)
    if history:
        rows = []
        for inv in history:
            rows.append({
                "Invoice": inv.get("invoice_number"),
                "Amount": f"{inv.get('currency','INR')} {float(inv.get('total_amount') or 0):,.2f}",
                "PO": inv.get("po_reference"),
                "Status": inv.get("overridden_status") or inv.get("status"),
                "Processed at": inv.get("uploaded_at"),
                "Run ID": inv.get("id"),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No invoices recorded for this vendor yet.")


def assistant_page() -> None:
    render_hero(
        "AP assistant.",
        "Ask plain English questions about ready-to-pay invoices, PO consumption, duplicates, tolerance issues, and recent rejections.",
    )
    decisions = all_decisions()
    examples = [
        "Which invoices are ready to pay?",
        "Show all invoices exceeding PO tolerance.",
        "How much is consumed on PO-2026-0014?",
        "Why was the latest invoice rejected?",
        "Queue summary",
    ]
    st.markdown('<div class="panel"><h3>Example questions</h3><p class="subtle">Click to try, or type your own.</p></div>', unsafe_allow_html=True)
    cols = st.columns(len(examples))
    for col, sample in zip(cols, examples):
        if col.button(sample, use_container_width=True):
            st.session_state["assistant_q"] = sample
    query = st.text_input("Your question", value=st.session_state.get("assistant_q", ""), placeholder="e.g. Which invoices are ready to pay?")
    if query:
        answer = answer_question(query, decisions)
        formatted = answer.replace("\n", "<br>")
        st.markdown(f'<div class="assistant-bubble">{formatted}</div>', unsafe_allow_html=True)


def reference_page() -> None:
    render_hero(
        "Procurement memory.",
        "The mock PO and vendor master data that power matching, tolerance checks, vendor allow-listing, and bank verification.",
    )
    st.subheader("PO dataset")
    st.dataframe(pd.read_csv("data/pos.csv"), use_container_width=True)
    st.subheader("Approved vendors")
    st.dataframe(pd.read_csv("data/approved_vendors.csv"), use_container_width=True)


# ---------------- Dashboard ----------------


def dashboard_page() -> None:
    render_hero(
        "AP Operations Dashboard.",
        "Status, outputs, and history across every invoice run, with live workflow signals.",
    )
    decisions = all_decisions()
    if not decisions:
        st.info("No invoices processed yet. Try the Inbox or Upload page to get started.")
        return
    counts = queue_counts(decisions)
    total = len(decisions)
    approved = sum(1 for d in decisions if d.get("status") == "APPROVED")
    flagged = sum(1 for d in decisions if d.get("status") == "FLAGGED")
    rejected = sum(1 for d in decisions if d.get("status") == "REJECTED")
    total_amount = sum(float((d.get("extracted") or {}).get("total") or 0) for d in decisions)
    ready_amount = sum(
        float((d.get("extracted") or {}).get("total") or 0)
        for d in decisions
        if queue_for(d) == "Ready for Payment"
    )

    tiles = [
        ("Total processed", f"{total}", f"INR {total_amount:,.0f} total"),
        ("Auto approved", f"{approved}", f"{(approved/total*100):.0f}% of runs"),
        ("Needs review", f"{flagged}", "Flagged or routed"),
        ("Blocked", f"{rejected}", "Payment cannot proceed"),
    ]
    tiles_html = "".join(
        f'<div class="summary-tile"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>'
        for label, value, sub in tiles
    )
    st.html(f'<div class="summary-tiles">{tiles_html}</div>')

    st.markdown('<div class="section-label">Queue distribution</div>', unsafe_allow_html=True)
    queue_df = pd.DataFrame(
        [{"Queue": q, "Count": counts.get(q, 0)} for q in QUEUE_ORDER + ["Payment Blocked"]]
    )
    st.dataframe(queue_df, use_container_width=True, hide_index=True)

    st.markdown('<div class="section-label">Ready-to-pay value</div>', unsafe_allow_html=True)
    st.caption(f"INR {ready_amount:,.2f} across {counts.get('Ready for Payment', 0)} invoices.")

    st.markdown('<div class="section-label">Recent activity</div>', unsafe_allow_html=True)
    recent = sorted(decisions, key=lambda d: d.get("timestamp") or "", reverse=True)[:15]
    rows = []
    for d in recent:
        extracted = d.get("extracted") or {}
        vendor = extracted.get("vendor") or {}
        readiness = d.get("readiness") or {}
        rows.append({
            "Processed": (d.get("timestamp") or "")[:19],
            "Vendor": vendor.get("name"),
            "Invoice": extracted.get("invoice_number"),
            "Amount": f"{extracted.get('currency','INR')} {float(extracted.get('total') or 0):,.2f}",
            "PO": extracted.get("po_reference"),
            "Decision": d.get("status"),
            "Queue": readiness.get("queue"),
            "Readiness": f"{readiness.get('score', 0)}%",
            "Run ID": d.get("invoice_id"),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


# ---------------- Inbox ----------------


INBOX_STATUS_CLASS = {
    "New": "ist-new",
    "Processing": "ist-proc",
    "Reviewed": "ist-rev",
    "Paid": "ist-paid",
}

INBOX_STATUS_ORDER = ["New", "Processing", "Reviewed", "Paid"]


def inbox_page() -> None:
    render_hero(
        "Inbox simulation.",
        "Invoices arrive as PDF attachments by email. Triage each one, process the attachment, and watch status update as the workflow runs.",
    )
    emails = db.list_inbox()
    counts = db.inbox_counts()
    if not emails:
        st.info(
            "Inbox is empty. Seed it with sample vendor emails (using the bundled sample invoices)."
        )
        if st.button("Populate inbox with sample emails", type="primary"):
            added = seed_inbox_emails()
            st.success(f"Seeded {added} sample emails." if added else "Sample inbox already seeded.")
            st.rerun()
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("New", counts.get("New", 0))
    c2.metric("Processing", counts.get("Processing", 0))
    c3.metric("Reviewed", counts.get("Reviewed", 0))
    c4.metric("Paid", counts.get("Paid", 0))

    refresh_col, seed_col = st.columns([1, 1])
    with refresh_col:
        status_filter = st.selectbox(
            "Filter by status", ["All"] + INBOX_STATUS_ORDER, key="inbox_filter"
        )
    with seed_col:
        if st.button("Add more sample emails", use_container_width=True):
            added = seed_inbox_emails()
            st.toast(f"Added {added} new sample emails." if added else "All sample emails are already in your inbox.")
            st.rerun()

    visible = [e for e in emails if status_filter == "All" or e.get("status") == status_filter]
    if not visible:
        st.info(f"No emails in status '{status_filter}'.")
        return

    header = (
        '<div class="inbox-row header">'
        '<div>Sender</div><div>Subject</div><div>Vendor guess</div>'
        '<div>Received</div><div>Status</div></div>'
    )
    rows_html = [header]
    for e in visible:
        cls = INBOX_STATUS_CLASS.get(e.get("status", "New"), "ist-new")
        rows_html.append(
            '<div class="inbox-row">'
            f'<div><strong>{e.get("sender") or "—"}</strong></div>'
            f'<div>{e.get("subject") or "(no subject)"}<br><span class="subtle">{e.get("attachment_name") or ""}</span></div>'
            f'<div>{e.get("vendor_guess") or "—"}</div>'
            f'<div class="subtle">{(e.get("received_at") or "")[:19]}</div>'
            f'<div><span class="inbox-status {cls}">{e.get("status")}</span></div>'
            '</div>'
        )
    st.html('<div class="panel">' + "".join(rows_html) + "</div>")

    st.markdown('<div class="section-label">Open email</div>', unsafe_allow_html=True)
    pick = st.selectbox(
        "Pick an email to triage",
        [e["id"] for e in visible],
        format_func=lambda eid: next((f"{e['sender']} — {e['subject']}" for e in visible if e['id'] == eid), eid),
    )
    if pick:
        email = db.get_inbox_email(pick) or {}
        st.markdown(
            f"""
            <div class="panel">
                <div class="eyebrow">From</div>
                <p><strong>{email.get('sender')}</strong></p>
                <div class="eyebrow">Subject</div>
                <p>{email.get('subject')}</p>
                <div class="eyebrow">Attachment</div>
                <p>{email.get('attachment_name')} <span class="subtle">· vendor guess {email.get('vendor_guess') or '—'}</span></p>
                <div class="eyebrow">Message</div>
                <div class="comment-bubble">{(email.get('body') or '').replace(chr(10), '<br>')}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        c1, c2, c3 = st.columns(3)
        process_clicked = c1.button("Process attachment", type="primary", use_container_width=True, disabled=bool(email.get("run_id")))
        c2.button(
            "Mark as Reviewed",
            use_container_width=True,
            on_click=lambda: db.update_inbox_status(pick, "Reviewed"),
        )
        c3.button(
            "Mark as Paid",
            use_container_width=True,
            on_click=lambda: db.update_inbox_status(pick, "Paid"),
        )

        if email.get("run_id"):
            st.success(f"Already processed as run {email['run_id']}.")
            if st.button("Open in Invoice Detail"):
                st.session_state["selected_run"] = email["run_id"]
                st.session_state["nav_page"] = "Invoice Detail"
                st.rerun()
        elif process_clicked and email.get("pdf_path"):
            db.update_inbox_status(pick, "Processing")
            with st.status("Running Zamp AP workflow on attachment", expanded=True) as status:
                decision, events = process_invoice(email["pdf_path"], email.get("attachment_name") or "inbox.pdf")
                for ev in events:
                    st.write(f"{ev.stage_name}: {ev.output_summary or 'complete'}")
                status.update(label="Decision ready", state="complete")
            db.update_inbox_status(pick, "Reviewed", run_id=decision.invoice_id)
            render_decision_card(decision.model_dump(mode="json"))
            st.success("Attachment processed and linked to the email.")


# ---------------- Bulk upload ----------------


def bulk_page() -> None:
    render_hero(
        "Bulk invoice processing.",
        "Drop a batch of vendor PDFs. Zamp will classify, extract, validate, and decide each one — then summarize what's ready to pay vs. blocked.",
    )
    uploaded = st.file_uploader(
        "Invoice PDFs",
        type=["pdf"],
        accept_multiple_files=True,
        label_visibility="collapsed",
    )
    if not uploaded:
        st.caption("Select one or more PDFs to start a batch.")
        return
    if not st.button(f"Process batch of {len(uploaded)} invoice(s)", type="primary"):
        return

    progress = st.progress(0.0, text="Starting batch…")
    placeholder = st.empty()
    results: list[dict] = []
    failures: list[dict] = []
    for idx, f in enumerate(uploaded):
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(f.getvalue())
                tmp_path = Path(tmp.name)
            decision, _ = process_invoice(tmp_path, f.name)
            tmp_path.unlink(missing_ok=True)
            d = decision.model_dump(mode="json")
            results.append(d)
            placeholder.write(
                f"✓ {f.name}: {d.get('status')} · readiness {(d.get('readiness') or {}).get('score', 0)}%"
            )
        except Exception as exc:
            failures.append({"filename": f.name, "error": str(exc)})
            placeholder.write(f"✗ {f.name}: extraction failed ({exc})")
        progress.progress((idx + 1) / len(uploaded), text=f"Processed {idx + 1} / {len(uploaded)}")

    progress.empty()
    placeholder.empty()

    total = len(uploaded)
    processed = len(results)
    failed = len(failures)
    ready = sum(1 for d in results if queue_for(d) == "Ready for Payment")
    review = sum(1 for d in results if d.get("status") == "FLAGGED")
    blocked = sum(1 for d in results if d.get("status") == "REJECTED")

    tiles = [
        ("Total uploaded", f"{total}", "Files received"),
        ("Processed successfully", f"{processed}", f"{processed/total*100:.0f}% of batch" if total else ""),
        ("Failed extraction", f"{failed}", "Could not parse PDF" if failed else "None"),
        ("Ready to pay", f"{ready}", "Auto-approved"),
        ("Needs review", f"{review}", "Routed to queues"),
        ("Blocked", f"{blocked}", "Critical failures"),
    ]
    tiles_html = "".join(
        f'<div class="summary-tile"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>'
        for label, value, sub in tiles
    )
    st.html(f'<div class="summary-tiles">{tiles_html}</div>')

    if results:
        rows = []
        for d in results:
            extracted = d.get("extracted") or {}
            readiness = d.get("readiness") or {}
            rows.append({
                "Vendor": (extracted.get("vendor") or {}).get("name"),
                "Invoice": extracted.get("invoice_number"),
                "Amount": f"{extracted.get('currency','INR')} {float(extracted.get('total') or 0):,.2f}",
                "PO": extracted.get("po_reference"),
                "Decision": d.get("status"),
                "Queue": readiness.get("queue"),
                "Readiness": f"{readiness.get('score', 0)}%",
                "Run ID": d.get("invoice_id"),
            })
        st.markdown('<div class="section-label">Batch results</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    if failures:
        st.markdown('<div class="section-label">Failed files</div>', unsafe_allow_html=True)
        st.dataframe(pd.DataFrame(failures), use_container_width=True, hide_index=True)


# ---------------- SLA / Aging ----------------


def aging_bucket(days: int) -> tuple[str, str]:
    if days <= 7:
        return ("0–7 days", "age-ok")
    if days <= 30:
        return ("8–30 days", "age-warn")
    return ("30+ days", "age-bad")


def sla_page() -> None:
    render_hero(
        "Aging & SLA dashboard.",
        "Prioritize by days since received, payment due date, and SLA breach risk.",
    )
    decisions = all_decisions()
    if not decisions:
        st.info("No invoices to age yet.")
        return
    today = datetime.now(timezone.utc).date()
    rows = []
    breach_count = 0
    overdue_count = 0
    for d in decisions:
        extracted = d.get("extracted") or {}
        vendor = extracted.get("vendor") or {}
        timestamp = d.get("timestamp")
        received_days = days_between(timestamp, today) or 0
        due_in = days_until(extracted.get("due_date"), today)
        bucket, age_cls = aging_bucket(received_days)
        if d.get("status") != "APPROVED" and received_days > 7:
            breach_count += 1
            sla_text = f'<span class="aging-pill age-bad">SLA at risk</span>'
        else:
            sla_text = f'<span class="aging-pill age-ok">On track</span>'
        if due_in is not None and due_in < 0 and d.get("status") != "APPROVED":
            overdue_count += 1
            due_text = f"Overdue {abs(due_in)}d"
            due_cls = "age-bad"
        elif due_in is not None and due_in < 7:
            due_text = f"Due in {due_in}d"
            due_cls = "age-warn"
        elif due_in is not None:
            due_text = f"Due in {due_in}d"
            due_cls = "age-ok"
        else:
            due_text = "No due date"
            due_cls = "age-warn"
        rows.append({
            "Invoice": extracted.get("invoice_number"),
            "Vendor": vendor.get("name"),
            "Amount": f"{extracted.get('currency','INR')} {float(extracted.get('total') or 0):,.2f}",
            "Received age": received_days,
            "Bucket": bucket,
            "Bucket class": age_cls,
            "Due": due_text,
            "Due class": due_cls,
            "Status": d.get("status"),
            "SLA": sla_text,
            "Run ID": d.get("invoice_id"),
        })

    rows.sort(key=lambda r: r["Received age"], reverse=True)

    c1, c2, c3 = st.columns(3)
    c1.metric("In-flight invoices", len(rows))
    c2.metric("SLA at risk", breach_count)
    c3.metric("Overdue payments", overdue_count)

    header = (
        '<div class="aging-row header">'
        '<div>Invoice / Vendor</div><div>Amount</div><div>Received age</div>'
        '<div>Due</div><div>Status</div><div>SLA</div></div>'
    )
    body = []
    for r in rows[:50]:
        body.append(
            '<div class="aging-row">'
            f'<div><strong>{r["Invoice"] or "—"}</strong><br><span class="subtle">{r["Vendor"] or "—"}</span></div>'
            f'<div>{r["Amount"]}</div>'
            f'<div><span class="aging-pill {r["Bucket class"]}">{r["Received age"]}d · {r["Bucket"]}</span></div>'
            f'<div><span class="aging-pill {r["Due class"]}">{r["Due"]}</span></div>'
            f'<div>{r["Status"]}</div>'
            f'<div>{r["SLA"]}</div>'
            '</div>'
        )
    st.html('<div class="panel">' + header + "".join(body) + "</div>")


# ---------------- Payment runs ----------------


def _payment_run_candidates(decisions: list[dict]) -> list[dict]:
    return [
        d for d in decisions
        if queue_for(d) == "Ready for Payment"
        or (d.get("overridden_status") == "APPROVED")
    ]


def payment_run_page() -> None:
    render_hero(
        "Payment run summary.",
        "Preview every invoice that will be exported, totals by vendor, high-value payments, and any overrides — before you release the batch.",
    )
    decisions = all_decisions()
    candidates = _payment_run_candidates(decisions)
    if not candidates:
        st.info("No invoices are currently in Ready-for-Payment status. Process or approve some first.")
        prior = db.list_payment_runs()
        if prior:
            st.markdown('<div class="section-label">Prior payment runs</div>', unsafe_allow_html=True)
            st.dataframe(pd.DataFrame(prior), use_container_width=True, hide_index=True)
        return

    total = sum(float((d.get("extracted") or {}).get("total") or 0) for d in candidates)
    vendor_set = {((d.get("extracted") or {}).get("vendor") or {}).get("name") for d in candidates}
    overrides = [d for d in candidates if d.get("overridden_status") == "APPROVED"]
    high_value = [d for d in candidates if float((d.get("extracted") or {}).get("total") or 0) >= 100000]

    payment_date = st.date_input(
        "Payment date",
        value=datetime.now(timezone.utc).date(),
    )

    tiles = [
        ("Invoices to pay", f"{len(candidates)}", "From Ready queue"),
        ("Total amount", f"INR {total:,.2f}", "Currency: INR"),
        ("Vendors included", f"{len(vendor_set)}", "Unique"),
        ("High-value (≥1L)", f"{len(high_value)}", "Manual review recommended"),
    ]
    tiles_html = "".join(
        f'<div class="summary-tile"><div class="label">{label}</div>'
        f'<div class="value">{value}</div><div class="sub">{sub}</div></div>'
        for label, value, sub in tiles
    )
    st.html(f'<div class="summary-tiles">{tiles_html}</div>')

    if overrides:
        st.markdown(
            f'<div class="why-panel"><div class="eyebrow">Overrides included</div>'
            f'<p>{len(overrides)} invoice(s) included on the basis of a human override rather than '
            f'machine approval. Confirm with the relevant approver before sending the file to the bank.</p></div>',
            unsafe_allow_html=True,
        )

    rows = []
    for d in candidates:
        extracted = d.get("extracted") or {}
        vendor = extracted.get("vendor") or {}
        rows.append({
            "Vendor": vendor.get("name"),
            "Invoice": extracted.get("invoice_number"),
            "Amount": f"{extracted.get('currency','INR')} {float(extracted.get('total') or 0):,.2f}",
            "Bank account": extracted.get("bank_account"),
            "PO": extracted.get("po_reference"),
            "Override?": "Yes" if d.get("overridden_status") == "APPROVED" else "No",
            "Run ID": d.get("invoice_id"),
        })
    st.markdown('<div class="section-label">Invoices in this batch</div>', unsafe_allow_html=True)
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    csv = export_payment_batch_csv(decisions)
    c1, c2 = st.columns([1, 1])
    with c1:
        if csv:
            st.download_button(
                "Download payment batch CSV",
                data=csv,
                file_name=f"zamp_payment_batch_{payment_date.isoformat()}.csv",
                mime="text/csv",
                type="primary",
            )
    with c2:
        if st.button("Save payment run", use_container_width=True):
            run_id = str(uuid.uuid4())
            db.save_payment_run({
                "id": run_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "payment_date": payment_date.isoformat(),
                "total_amount": total,
                "invoice_count": len(candidates),
                "vendor_count": len(vendor_set),
                "details": {
                    "invoices": [r["Run ID"] for r in rows],
                    "overrides": [d.get("invoice_id") for d in overrides],
                    "high_value": [d.get("invoice_id") for d in high_value],
                },
            })
            st.success(f"Payment run {run_id[:8]} saved.")

    prior = db.list_payment_runs()
    if prior:
        st.markdown('<div class="section-label">Prior payment runs</div>', unsafe_allow_html=True)
        prior_rows = []
        for r in prior:
            prior_rows.append({
                "Created": r.get("created_at", "")[:19],
                "Payment date": r.get("payment_date"),
                "Invoices": r.get("invoice_count"),
                "Vendors": r.get("vendor_count"),
                "Total": f"INR {float(r.get('total_amount') or 0):,.2f}",
                "Run ID": r.get("id"),
            })
        st.dataframe(pd.DataFrame(prior_rows), use_container_width=True, hide_index=True)


st.sidebar.markdown(
    """
    <div class="sidebar-brand">
        <span class="brand-mark">Z</span>
        <div>
            <div class="sidebar-brand-name">Zamp AI</div>
            <div class="sidebar-brand-sub">AP Automation Console</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)
NAV_PAGES = [
    "Dashboard",
    "Inbox",
    "Upload & Live Run",
    "Bulk Upload",
    "Exception Queue",
    "Aging & SLA",
    "Invoice Detail",
    "PO Consumption",
    "Vendor Risk",
    "Payment Runs",
    "AP Assistant",
    "POs & Vendors",
]

if "nav_page" in st.session_state and st.session_state["nav_page"] in NAV_PAGES:
    default_index = NAV_PAGES.index(st.session_state["nav_page"])
    st.session_state.pop("nav_page", None)
else:
    default_index = 0

page = st.sidebar.radio("Navigate", NAV_PAGES, index=default_index)
st.sidebar.markdown("---")

PAGE_MAP = {
    "Dashboard": dashboard_page,
    "Inbox": inbox_page,
    "Upload & Live Run": upload_page,
    "Bulk Upload": bulk_page,
    "Exception Queue": queue_page,
    "Aging & SLA": sla_page,
    "Invoice Detail": detail_page,
    "PO Consumption": po_consumption_page,
    "Vendor Risk": vendor_risk_page,
    "Payment Runs": payment_run_page,
    "AP Assistant": assistant_page,
    "POs & Vendors": reference_page,
}

PAGE_MAP[page]()
