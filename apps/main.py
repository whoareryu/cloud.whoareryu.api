from fastapi import FastAPI


from apps.titanic.app.james_controller import JamesController
from apps.doro.app.doro_director import DoroDirector

app = FastAPI(title="Whoareryu Main Page")

@app.get("/")
def read_root():
    return {"message": "FastAPI 메인 페이지.", "docs": "/docs"}

@app.get("/titanic/data")
def read_titanic_data():
    james = JamesController()
    df = james.get_data()

    return df.to_dict(orient="records")

@app.get("/titanic/count")
def read_titanic_count():
    james = JamesController()
    count = james.get_count()
    return {"count": count}

@app.get("/titanic/count_survived")
def read_titanic_count_survived():
    james = JamesController() 
    count_survived = james.get_count_survived()
    return {"count_survived": count_survived}

@app.get("/titanic/count_dead")
def read_titanic_count_dead():
    james = JamesController()
    count_dead = james.get_count_dead()
    return {"count_dead": count_dead}

@app.get("/titanic/tree")
def read_titanic_tree():
    james = JamesController ()
    tree = james.has_decision_tree_model()
    return {"tree": tree}

@app.get("/titanic/model")
@app.get("/titanic/model_name")
def read_titanic_model():
    james = JamesController()
    model = james.get_training_model_name()
    return {"model": model}


@app.get("/doro/data")
def read_doro_data():
    doro = DoroDirector()
    df = doro.get_data()

    return df.to_dict(orient="records")



if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)




