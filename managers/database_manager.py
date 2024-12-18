from sqlalchemy.orm import sessionmaker

class DatabaseManager:
    def __init__(self, logger, engine):
        self.logger = logger
        try:
            # create a session
            Session = sessionmaker(bind=engine)
            self.session = Session()
            self.logger.debug("Connected to the database")
        except Exception as e:
            self.logger.error("An error occurred: %s", e)
            raise e

    def __enter__(self):
        self.logger.info("Transaction started.")
        return self.session

    def __exit__(self, exc_type, exc_value, traceback):
        if exc_type is None:
            self.logger.info("Transaction committed.")
            self.session.commit()
        else:
            self.logger.error(f"Transaction rolled back due to: {exc_value}")
            self.session.rollback()
        self.session.close()
        self.logger.info("Session closed.")
        return False