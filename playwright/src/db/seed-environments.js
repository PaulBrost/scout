// SCOUT — Seed default environment and assessments
// Run with: node src/db/seed-environments.js

const path = require('path');
require('dotenv').config({ path: path.resolve(__dirname, '../../.env') });
const db = require('./index');

async function seed() {
  // Check if default environment already exists
  const existing = await db.query("SELECT id FROM environments WHERE is_default = true");
  if (existing.rows.length > 0) {
    console.log('Default environment already exists:', existing.rows[0].id);
    console.log('Skipping seed. Delete it first to re-seed.');
    return;
  }

  // Insert the default NAEP Review environment
  const envResult = await db.query(`
    INSERT INTO environments (name, base_url, auth_type, credentials, launcher_config, notes, is_default)
    VALUES ($1, $2, $3, $4, $5, $6, true)
    RETURNING id
  `, [
    'NAEP Review (Staging)',
    process.env.ASSESSMENT_URL || 'http://rt.ets.org/c3.NET/naep_review.aspx',
    'password_only',
    JSON.stringify({
      password: process.env.ASSESSMENT_PASSWORD || 'c3c4',
      password_selector: '#_ctl0_Body_PasswordText',
      submit_selector: '#_ctl0_Body_SubmitButton',
    }),
    JSON.stringify({
      launcher_selector: '#TheTest',
      submit_selector: 'input[type="submit"]',
      intro_screens: 5,
    }),
    'Default NAEP review environment for POC testing',
  ]);

  const envId = envResult.rows[0].id;
  console.log('Created environment:', envId);

  // Insert all 7 assessment forms
  const assessments = [
    ['cra-form1', 'CRA Form 1 — All Base', 'Mathematics', 'Grade 8', 'FY2025', 20,
     'tests/craFY25_form1_AllBase.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
     'Cognitive Research Assessment Form 1 with all baseline item variants.'],
    ['cra-form2', 'CRA Form 2 — All Variant', 'Mathematics', 'Grade 8', 'FY2025', 20,
     'tests/craFY25_form2_AllVar.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
     'CRA Form 2 with all variant item versions.'],
    ['cra-form3', 'CRA Form 3 — Odd Var / Even Base', 'Mathematics', 'Grade 8', 'FY2025', 20,
     'tests/craFY25_form3_OddVarEvenBase.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
     'CRA Form 3 mixing odd-variant and even-baseline items.'],
    ['cra-form4', 'CRA Form 4 — Odd Base / Even Var', 'Mathematics', 'Grade 8', 'FY2025', 20,
     'tests/craFY25_form4_OddBaseEvenVar.xml|Pure/prefs/NAEP_CRA_Sept2024.xml',
     'CRA Form 4 mixing odd-baseline and even-variant items.'],
    ['math-fluency', 'Math Fluency', 'Mathematics', 'Grades 4 & 8', 'FY2022', null,
     'tests/mathFluency.xml|Pure/prefs/NAEP_MF_2022.xml',
     'Timed math fluency assessment.'],
    ['naep-id-4th', 'NAEP ID — 4th Grade', 'General', 'Grade 4', 'FY2022', null,
     'tests/naepID_4thGrade.xml|Pure/prefs/NAEP_ID_2022.xml',
     'NAEP identification and demographic form for 4th grade.'],
    ['naep-id-8th', 'NAEP ID — 8th Grade', 'General', 'Grade 8', 'FY2022', null,
     'tests/naepID_8thGrade.xml|Pure/prefs/NAEP_ID_2022.xml',
     'NAEP identification and demographic form for 8th grade.'],
  ];

  for (const [id, name, subject, grade, year, itemCount, formValue, description] of assessments) {
    await db.query(`
      INSERT INTO assessments (id, environment_id, name, subject, grade, year, item_count, form_value, description)
      VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
      ON CONFLICT (id) DO UPDATE SET
        environment_id = $2, name = $3, subject = $4, grade = $5,
        year = $6, item_count = $7, form_value = $8, description = $9,
        updated_at = now()
    `, [id, envId, name, subject, grade, year, itemCount, formValue, description]);
  }

  console.log('Seeded', assessments.length, 'assessments');
}

seed()
  .then(() => { console.log('Done'); process.exit(0); })
  .catch(e => { console.error('Seed error:', e.message); process.exit(1); });
