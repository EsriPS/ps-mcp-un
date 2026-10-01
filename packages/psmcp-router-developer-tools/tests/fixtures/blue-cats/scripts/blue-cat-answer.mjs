#!/usr/bin/env node

const prompt = process.argv.slice(2).join(" ").trim();
const subject = prompt || "the cat";

console.log(`${subject} is blue.`);
