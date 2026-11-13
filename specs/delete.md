# Spec: Delete

Status: draft 2026-11-13; finalised when its plan is written. Module `delete` in the [map](README.md). Depends on slices 2 to 6 and 9.

## Objective

Delete is for mistakes: the thing should never have existed. It is different from dropping a task, which is a decision and stays in history. A deleted row is hidden everywhere but stays in the database, so the delete reaches the person's other devices.

The column and the filter are there from slice 1; this slice adds the routes and decides what each delete takes with it.

References: [`data-model.md`](../../docs/data-model.md#drop-and-delete), front-end issue #38.

## Scope

**In:**

- Routes: `deleteTask`, `deleteMilestone`, `deleteGoal`, `deleteAspiration`, `deleteRecurringItem`.
- What goes along, in the same transaction:

  | Deleting | Also deletes | Leaves |
  | --- | --- | --- |
  | A task | Its week records | |
  | A milestone | Its check-ins | The goal's other milestones, renumbered |
  | A goal | Its tasks and their week records, milestones, check-ins, weekly targets, quit days, urge ratings | A recurring item continued from it, with its from-goal emptied |
  | An aspiration | | Its goals and recurring items, with no aspiration; the other aspirations, renumbered |
  | A recurring item | Its open tasks | Its done tasks, with no item |

- A pass over every unique index to make sure it ignores deleted rows.
- A pass over every read to prove deleted rows never appear.

**Out (later):**

- Undo, a bin, or restoring from the audit log.
- Removing rows from the database for good.
- Deleting the account (`sign-in`).

## Testing strategy

As shared, plus: for each row of the table, everything that should go is gone from every read and everything that should stay is there; deleting twice changes nothing; a new row can reuse what a deleted one held (a position, a generated task's period and number).

## Boundaries

As shared. **Never:** a hard delete from application code; a delete that leaves a visible row pointing at a hidden one.

## Success criteria

- [ ] Each of the five deletes hides the row and what goes with it, in one transaction.
- [ ] No read returns a deleted row.
- [ ] Every delete is in the audit log with its action.
- [ ] The four checks pass.

## Open questions

1. **Deleting an aspiration leaves its goals with none** (they move to Other goals). I made that call in issue #38 and it hasn't been confirmed.
2. **Deleting a recurring item:** I've assumed its open tasks go and its done ones stay as history. The alternative is that everything it made goes, as with a goal.
3. **A deleted generated task and the week.** If a session of this week's target is deleted, turnover mustn't recreate it. Either the unique rule counts deleted rows for generated tasks, or deleting a generated task isn't offered and dropping is the answer.
4. **Is an undo wanted for the few seconds after a delete?** The front end may show one; the API would need an `undelete`.
