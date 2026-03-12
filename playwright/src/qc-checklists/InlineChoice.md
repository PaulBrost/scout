QA/QC Instructions for Item Type – Inline Choice
# Inline Choice: Overview
Inline choice item type requires test takers to respond by selecting an option from a dropdown list. Menu options can include images, MathML, or styled (italic, bold, underlined) text.
Appearance:
- Each dropdown list is blank by default upon first entry to the item as the unselected/unanswered state.
- The first option within the dropdown menu is also always blank.
- Clear Answer button is always provided at the bottom
Types:
- Single select inline choice - with only one dropdown option available

- Multi select inline choice (more widely used) - when more than one dropdown option is available

Dropdown Menus:
- The dropdown menu opens when the associated button is selected and closes when you select the button again or either tap or click elsewhere on the screen
- By default, the dropdown menu opens downward. The menu only opens upwards when the menu options would be cut off by the bottom of the browser window (e.g. when zoomed)
- The dropdown menu options can include regular or style text (italic, bold, underline), images, or MathML
- Only one dropdown can be opened at a time
- Each dropdown menu is as wide as its widest available option
- A scroll bar in the dropdown menu appears when the options exceed the available screen space
# Inline Choice: QC Checklist


|  | Test | Steps to Test | Expected Results |
| --- | --- | --- | --- |
| 1. | Verify that each option in the drop-down menu can be selected. | Entering the item (before selections are made), an empty value is presented in the drop-down box. Select the drop-down arrow () to open the drop-down menu. Select the first option, then the second, then the third, etc., until each option has been selected. | The selected option should appear in the drop-down box.  The width of the option selected should fit within the box and not overlap or touch the drop-down arrow.  Verify the options menu opens down by default, not upwards.  It opens upwards only when it is cut off by the bottom of the browser window or when using zoom Scrollbar will appear with many options present The font and font size of the option should be consistent and appropriate based on whether it is text, mathML or a combination of text and mathML. |
| 2. | Verify that each selected option from the drop-down menu can be cleared. | Test 1:   Select an option from the drop-down menu and then select Clear Answer.     Test 2:   Select an option from the drop-down menu and then select the empty value option.    NOTE: Pay special attention to any options that are overlaying the Clear Answer button to confirm it is selecting the option and not clearing it.   [Do this test for each option.] | In both tests, there should be no option seen in the drop-down box. |
| 3. | Verify that each selected option is retained.     NOTE: This can only be tested in an assembled block. | Select an option from the drop-down menu and then navigate to the next item. Then, navigate back to the inline choice item.     [Do this test for each option. In addition, vary your navigation. For instance, go to the next item on some and go to an item that is not the next item (before and after) for others.] | The option selected from the drop-down menu should appear in the drop-down box. |
| 4. | Verify that a cleared answer is NOT retained.     NOTE: This can only be tested in an assembled block. | Select an option from the drop-down menu and then navigate to the next item. Then, navigate back to the inline choice item. Select Clear Answer and then navigate to the next item and then back.     [Do this test for various sets of options. In addition, vary your navigation. For instance, go to the next item on some and go to an item that is not the next item (before and after) for others. Also do this test by selecting the empty value in the drop-down menu instead of Clear Answer.] | The tab for the inline choice item should not show as answered, and no option in the item should appear in the drop-down menu. In addition, the item should appear as not answered on the Review tab. |
| 5. | Verify that the options in the drop-down menu are read by the TTS engine. | Test 1:   Entering the item (before selections are made), activate TTS and select the element that contains the inline choice drop-down menu(s).     Test 2:   Select an option from the drop-down menu(s). Then, activate TTS and select the element that contains the inline choice drop-down menu(s). | The sentence or paragraph is read up to the dropdown, the dropdown opens automatically, and each option is read in sequence, the dropdown closes automatically, and the rest of the sentence or paragraph is read.  It should only read the option selected along with the sentence or paragraph. |
