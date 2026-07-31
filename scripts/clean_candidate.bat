@echo off
cd /d "%~dp0.."
if exist candidate_output rmdir /s /q candidate_output
mkdir candidate_output
