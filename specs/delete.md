# Spec: Delete

Status: finalised 2026-11-19 with its plan ([`../tasks/plan.md`](../tasks/plan.md)). Issue: [#12](https://github.com/jan-mcsparin/goals-to-actions-api/issues/12). Module `delete` in the [map](README.md). Depends on slices 2 to 6 and 9.

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
  | A recurring item | Its open tasks | Its done tasks, with the link to the item emptied; they keep the origin recurring item |

- A pass over every unique index to make sure it ignores deleted rows, except the one on generated tasks: a deleted session's period and number stay taken, so turnover never makes it again.
- A pass over every read to prove deleted rows never appear.

**Out (later):**

- Undo, a bin, or restoring from the audit log.
- Removing rows from the database for good.
- Deleting the account (`sign-in`).

## Testing strategy

As shared, plus: for each row of the table, everything that should go is gone from every read and everything that should stay is there; deleting twice changes nothing; a new row can reuse a position a deleted one held; a deleted generated task is not made again when its week is opened twice.

## Boundaries

As shared. **Never:** a hard delete from application code; a delete that leaves a visible row pointing at a hidden one.

## Success criteria

- [ ] Each of the five deletes hides the row and what goes with it, in one transaction.
- [ ] No read returns a deleted row.
- [ ] Every delete is in the audit log with its action.
- [ ] The front end's types are regenerated from the new schema and its mock client compiles against them.
- [ ] The four checks pass.

## Settled

- **Deleting an aspiration leaves its goals and recurring items with none** (they move to Other goals). Jan, 2026-11-19.
- **Deleting a recurring item takes its open tasks; its done ones stay as history,** with the link to the item emptied and the origin kept. Jan, 2026-11-19.
- **No undo.** The front end asks once before deleting. Jan, 2026-11-19.
- 2026-11-16: the unique rule for generated tasks counts deleted rows, so a deleted session stays deleted.
