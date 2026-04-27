import re
import structlog
from app.infrastructure.claude_client import ClaudeClient
from app.services.schema_service import SchemaService
from app.prompts.nl_to_sql import NL_TO_SQL_SYSTEM_PROMPT, FEW_SHOT_EXAMPLES_TEMPLATE
from app.exceptions import OutOfScopeError

logger = structlog.get_logger(__name__)

DEFAULT_FEW_SHOT = [
    {
        "question": "How many transactions are in the database?",
        "sql": ("SELECT COUNT(*) AS total_transactions "
                "FROM [dbo].[tblTransactionalData]")
    },
    {
        "question": "What are the top 10 accounts by total value?",
        "sql": ("SELECT TOP 10 t.AccountID, c.AccountDescription, "
                "SUM(t.Value) AS total_value "
                "FROM [dbo].[tblTransactionalData] t "
                "JOIN [dbo].[tblChartOfAccounts] c ON t.AccountID = c.AccountID "
                "GROUP BY t.AccountID, c.AccountDescription "
                "ORDER BY total_value DESC")
    },
    {
        "question": "Show me all transactions for period Jan2022",
        "sql": ("SELECT TransactionID, AccountID, LegalEntity, Value, Period "
                "FROM [dbo].[tblTransactionalData] "
                "WHERE Period = 'Jan2022' "
                "ORDER BY Value DESC")
    },
    {
        "question": "What is the total value per legal entity?",
        "sql": ("SELECT LegalEntity, "
                "SUM(Value) AS total_value, "
                "COUNT(*) AS transaction_count "
                "FROM [dbo].[tblTransactionalData] "
                "GROUP BY LegalEntity "
                "ORDER BY total_value DESC")
    },
    {
        "question": "Show me all exchange rates for a specific period",
        "sql": ("SELECT Description, Category, Period, Rate, Fraction "
                "FROM [dbo].[tblExchangeRates] "
                "ORDER BY Period, Description")
    },
]


class NLToSQLEngine:
    """Converts natural language questions to SQL using Claude API."""

    def __init__(self, claude_client: ClaudeClient, schema_service: SchemaService,
                 few_shot_examples: list[dict] | None = None):
        self._claude = claude_client
        self._schema_service = schema_service
        self._few_shot = few_shot_examples or DEFAULT_FEW_SHOT

    async def generate_sql(self, question: str) -> str:
        """Generate a SQL query from a natural language question."""
        tables = await self._schema_service.get_tables()
        schema_text = self._schema_service.format_for_prompt(tables)

        examples_text = "\n".join(
            FEW_SHOT_EXAMPLES_TEMPLATE.format(**ex) for ex in self._few_shot
        )

        system_prompt = NL_TO_SQL_SYSTEM_PROMPT.format(
            schema=schema_text,
            examples=examples_text,
        )

        raw_sql = await self._claude.complete(
            system_prompt=system_prompt,
            user_message=f"Question: {question}\nSQL:",
            temperature=0.0,
        )

        # Detect out-of-scope response from Claude
        if raw_sql.strip().upper().startswith("OUT_OF_SCOPE"):
            logger.info("question_out_of_scope", question=question)
            raise OutOfScopeError(question)

        sql = self._clean_sql(raw_sql)
        logger.info("sql_generated", question=question, sql=sql)
        return sql

    @staticmethod
    def _clean_sql(raw: str) -> str:
        """Strip markdown fencing, comments, trailing semicolons."""
        sql = raw.strip()
        sql = re.sub(r"^```(?:sql)?\s*", "", sql)
        sql = re.sub(r"\s*```$", "", sql)
        sql = sql.rstrip(";").strip()
        sql = re.sub(r"--.*$", "", sql, flags=re.MULTILINE)
        return sql.strip()
